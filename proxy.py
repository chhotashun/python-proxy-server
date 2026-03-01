import socket 
import threading 
from datetime import timedelta, datetime 
import time 
#print("Proxy running....")
port = 8888
block_url = set()
block_lock= threading.Lock()


cache_map = {}
cache_lock = threading.Lock()
cache_time = timedelta(seconds = 30)

def handle_client_request(client_socket):
    print("Recieved request\n")

    # read data sent by client 
    request = b''
    while True:
        try:
            data = client_socket.recv(1024)
            if not data:
                break 
            request = request + data 
            if b'\r\n\r\n' in request:
                break 
            #print(f"{data.decode('utf-8')}")
        except Exception as e:
            print("Error reading from client socket ")
            break 
    host, port = extract_host_port_from_request(request)
    host = host.strip().lower()
    if is_url_blocked(host):
        try:
            client_socket.sendall(b"HTTP/1.1 403 Forbidden\r\nConnection: close\r\n\r\nBlocked by proxy\r\n")
        except Exception as e:
            print(f"Error: {e}")
            
        client_socket.close()
        return 
    
    # depending on host and port handle http or https requests 
    # grab first token to see if it is https 
    #if is_url_blocked(host):

    temp = request.split(b'\r\n', 1)[0]
    request_line = temp.split()
    # request_line stores list as ["get", "example.com", etc]
    method = request_line[0]
    if method == b"CONNECT":
        print(f"[HTTPS] {temp.decode('utf-8', 'ignore')}")
        handle_https(client_socket, host, port)
    else:
        print(f"[HTTP] {temp.decode('utf-8', 'ignore')}")
        handle_http(client_socket, request, host, port)

def handle_http(client_socket, request, host, port):
    start_time = time.perf_counter()
    temp = request.split(b'\r\n',1)[0]
    request_line = temp.split()
    
    method = request_line[0]
    # cache stores the full url http://example.com/80 and its values as recorded time and response
    cache_key =  request_line[1]
    
    if method == b'GET':
        with cache_lock:
            if cache_key in cache_map:
                cache_recordedTime, cache_response = cache_map[cache_key]
                if datetime.now() - cache_recordedTime < cache_time:
                    try:
                        client_socket.sendall(cache_response)
                        print(f"Cached response for {cache_key} sent")

                        end_time = time.perf_counter()
                        print(f"[CACHE HIT] Time taken: {(end_time - start_time)*1000:.2f} ms")
                    except Exception as e:
                        print(f"Error exception {e}")
                    client_socket.close()
                    return 
                else:
                    print(f"Time expired for cache {cache_key}")
                    del cache_map[cache_key]

    destination_socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    try:
        destination_socket.connect((host, port))
        request = request.replace(b"Proxy-Connection: Keep-Alive", b"Proxy-Connection: close")
        request = request.replace(b"Connection: keep-alive", b"Connection: close")
        destination_socket.sendall(request)
        print("Recieved response\n")

        response_data = b''

        while True:
            data = destination_socket.recv(1024)
            if not data:
                break 
            response_data += data 
            client_socket.sendall(data)
        if method == b'GET' and response_data:
            with cache_lock:
                cache_map[cache_key] = (datetime.now(), response_data)
                print(f"Cached response for {cache_key}")
        end_time = time.perf_counter()
        print(f"[CACHE_MISS] Time taken: {(end_time - start_time)*1000:.2f} ms")
    except Exception as e:
            print(f"Error exception {e}")

    finally:
        destination_socket.close()
        client_socket.close()

def handle_https(client_socket, host, port):
    destination_socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    destination_socket.connect((host, port))
    client_socket.sendall(b"HTTP/1.1 200 Connection Established\r\n\r\n")

        # Start HTTPS tunnel for client destination
    client_thread = threading.Thread(target = send_data, args = (client_socket, destination_socket))
    destination_thread = threading.Thread(target = send_data, args = (destination_socket, client_socket))
    client_thread.start()
    destination_thread.start()

    client_thread.join()
    destination_thread.join()

    destination_socket.close()
    client_socket.close()

def send_data(source, destination):
    try:
        while True:
            data = source.recv(1024)
            if data:
                destination.sendall(data)
            else:
                break 
    except Exception as e:
        print(f"Error message: {e}")

def extract_host_port_from_request(request):
    # The function extracts and checks if the request is http or https
    # get the first line of request 
    request_line = request.split(b'\r\n', 1)[0]
    request_string = request_line.split()
    method = request_string[0]
    target_port = request_string[1]

    #handle https request 
    if method == b'CONNECT':
        if b":" in target_port: 
            host, port = target_port.split(b":", 1)
            host = host.decode()
            port = int(port)
        else:
            host = target_port.decode()
            port = 443
    else:
        host_string_start = request.find(b'Host: ') + len(b'Host: ')
        host_string_end = request.find(b'\r\n', host_string_start)
        host_string = request[host_string_start:host_string_end].decode('utf-8')
        port_pos = host_string.find(":")

        if port_pos == -1:
            port = 80 
            host = host_string

        else:
            port = int((host_string[(port_pos + 1):]))
            host = host_string[:port_pos]
    return host, port

    # the boolean is_url_blocked(host) function simply checks if the url is in the block set 
def is_url_blocked(host):
    with block_lock:
        return host in block_url

# the function should give user option to block url
def blockurl():
    while True:
        user_input = input("1) Add URL to blockset\n"
                           "2) Remove URL from blockset\n"
                           "3) Show blocked URL's\n"
                           "4) Exit\n"
                           "Please Enter Your Choice: \n")
        
        if user_input == "1":
            url_string = input("Enter URL to block: ").strip().lower()
            if url_string in block_url:
                print(f"{url_string} already blocked")
                continue 
            with block_lock:
                block_url.add(url_string)

        elif user_input == "2":
            url_string = input("Enter URL to remove: ").strip().lower()

            if url_string not in block_url:
                print(f"{url_string} not blocked")
                continue 

            with block_lock:
                block_url.remove(url_string)

        elif user_input == "3":
            if block_url:
                with block_lock:
                    for item in block_url:
                        print(item)
            else:
                print("No url blocked")

        elif user_input == "4":
            print("Exiting...")
            break 

        else:
            print("Invalid choice please try again ")
            continue 

server = socket.socket(socket.AF_INET, socket.SOCK_STREAM)

server.bind(('127.0.0.1', port))
server.listen(10)

print("Proxy running on 127.0.0.1")
threading.Thread(target = blockurl, daemon=True).start()

while True:
    client_socket, addr = server.accept()
    print(f"Accepted connection from {addr[0]}:{addr[1]}")

    # create thread to handle client request 

    client_handler = threading.Thread(target = handle_client_request, args = (client_socket,))
    client_handler.start()