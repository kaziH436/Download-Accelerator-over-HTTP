from socket import *

def main():
    # Create a TCP socket
    clientSock = socket(AF_INET, SOCK_STREAM)
        
    # Initialize server address
#    server_addr = ("www.google.com", 80)
    server_addr = ("www.cuny.edu", 80)
    
    # Connect to the server
    try:
        clientSock.connect(server_addr)
        print("Connected to the server...")
    except Exception as e:
        print("connect:", e)
        clientSock.close()
        return

    # Send HEAD request
#    request = "HEAD / HTTP/1.1\r\nHost: www.google.com\r\nConnection: close\r\n\r\n"
    request = "HEAD / HTTP/1.1\r\nHost: www.cuny.edu\r\nConnection: close\r\n\r\n"
    clientSock.send(request.encode())
    print(request)
    print("-----------------------------------------------------------")

    # Get the response & print it on the screen
    MSG_SIZE = 100000
    while True:
        response = clientSock.recv(MSG_SIZE)
        if not response:
            break
        print(response.decode())

    clientSock.close()

if __name__ == "__main__":
    main()
