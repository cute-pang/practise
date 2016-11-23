# -*- coding: utf-8 -*- 
import socket, select,ssl, sys

GLOBAL_LOCAL_IP = '127.0.0.1'
GLOBAL_LOCAL_PROT = 8080

PROXY_SERVER_IP = '127.0.0.1'
PROXY_SERVER_PORT = 8081

HOST = '127.0.0.1'
HTTPS_PROT = 8082

NODE_TYPE_NORMAL_CLIENT = 0
NODE_TYPE_NORMAL_SERVER = 1
NODE_TYPE_PROXY_CLIENT = 2
NODE_TYPE_PROXY_SERVER = 3

#超时时间
timeout = 10

#全局epoll
epoll = select.epoll()

def connect_to_remote(ip, port, need_warp):
    tcpCliSock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    tcpCliSock.settimeout(timeout)

    if not need_warp:
        tcpCliSock.connect((ip, port))
        return tcpCliSock
    
    #封装成ssl socket
    sock = ssl.wrap_socket(tcpCliSock)
    try:
        sock.connect((ip, port))
    except socket.timeout:
        #连接超时处理
        sock.close()
        sys.exit()
    return sock
'''
    #发送并接收数据
    sock.sendall(data)
    fp = sock.makefile('rb', 0)
    #读取http response状态
    status = fp.readline(line_len).split()[1]
'''

#全局node列表
g_node = {}
        
#节点类,用于传输上行或者下行流量
class node():
    def __init__(self):
        #上行/下行描述符，如果为-1，则使用sockfd收发数据
        self.upward_fd = -1
        self.downward_fd = -1
        self.conn = -1

        #设置节点收发缓冲区
        self.down_flow = None
        self.up_flow = None

        self.node_type = -1

    def handle_flow(self):
        #如果是普通的客户端节点
        if self.node_type is NODE_TYPE_NORMAL_CLIENT:
            #处理上行流量
            if self.up_flow is not None:
                byteswritten = self.conn.send(self.up_flow)
                self.up_flow = self.up_flow[byteswritten:]
                if len(self.up_flow) == 0:
                    self.up_flow = None
                epoll.modify(self.conn.fileno(), select.EPOLLIN)
            #处理下行流量
            if self.down_flow is not None:
                if self.downward_fd == -1:
                    sock = connect_to_remote(PROXY_SERVER_IP, PROXY_SERVER_PORT, False)
                    tmp_sk_fd = sock.fileno()
                    #初始化代理node
                    g_node[tmp_sk_fd] = node()
                    g_node[tmp_sk_fd].upward_fd = self.conn.fileno()
                    g_node[tmp_sk_fd].conn = sock
                    g_node[tmp_sk_fd].node_type = NODE_TYPE_NORMAL_SERVER
                    self.downward_fd = tmp_sk_fd
                    epoll.register(tmp_sk_fd, select.EPOLLIN)
                #拷贝数据，触发pollin事件
                g_node[self.downward_fd].down_flow = self.down_flow    
                self.down_flow = None
                epoll.modify(self.downward_fd, select.EPOLLOUT)
            
        #如果是代理节点客户端
        if self.node_type is NODE_TYPE_PROXY_CLIENT:
            #处理上行流量
            if self.up_flow is not None:
                byteswritten = self.conn.send(self.up_flow)
                self.up_flow = self.up_flow[byteswritten:]
                if len(self.up_flow) == 0:
                    self.up_flow = None
                epoll.modify(self.conn.fileno(), select.EPOLLIN)
            #处理下行流量
            if self.down_flow is not None:
                if self.downward_fd == -1:
                    sock = connect_to_remote(HOST, HTTPS_PROT, False)
                    tmp_sk_fd = sock.fileno()
                    #初始化代理node
                    g_node[tmp_sk_fd] = node()
                    g_node[tmp_sk_fd].upward_fd = self.conn.fileno()
                    g_node[tmp_sk_fd].conn = sock
                    g_node[tmp_sk_fd].node_type = NODE_TYPE_PROXY_SERVER
                    self.downward_fd = tmp_sk_fd
                    epoll.register(tmp_sk_fd, select.EPOLLIN)
                #拷贝数据，触发pollin事件
                g_node[self.downward_fd].down_flow = self.down_flow    
                self.down_flow = None
                epoll.modify(self.downward_fd, select.EPOLLOUT)
            
        #如果是普通/代理的服务端节点
        if self.node_type is NODE_TYPE_NORMAL_SERVER or NODE_TYPE_PROXY_SERVER:
            #处理下行流量
            if self.down_flow is not None:
                byteswritten = self.conn.send(self.down_flow)
                self.down_flow = self.down_flow[byteswritten:]
                if len(self.down_flow) == 0:
                    self.down_flow = None
                epoll.modify(self.conn.fileno(), select.EPOLLIN)
            #处理上行流量
            if self.up_flow is not None:
                g_node[self.upward_fd].up_flow = self.up_flow
                self.up_flow = None
                epoll.modify(self.upward_fd, select.EPOLLOUT)

    def handle_close(self):
        #关闭下一跳节点
        if self.downward_fd != -1:
            epoll.modify(self.downward_fd, 0)
            epoll.unregister(self.downward_fd)
            g_node[self.downward_fd].conn.shutdown(socket.SHUT_RDWR)
            g_node[self.downward_fd].conn.close()
            del g_node[self.downward_fd]

        #关闭本节点
        node_fd = self.conn.fileno()
        epoll.modify(node_fd, 0)
        epoll.unregister(node_fd)
        self.conn.shutdown(socket.SHUT_RDWR)
        self.conn.close()
        del g_node[node_fd]
    
    '''
    def resolve_dns(self):
        #先用最简单的方式，可以扩展
        return socket.gethostby_name(self.flow.host)
    '''
        
        