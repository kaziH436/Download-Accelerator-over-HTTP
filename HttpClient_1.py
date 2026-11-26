from socket import *

def main():
    # Create a TCP socket
    clientSock = socket(AF_INET, SOCK_STREAM)
        
    # Set the send buffer size to 5000 bytes
    clientSock.setsockopt(SOL_SOCKET, SO_RCVBUF, 5000) 

    # Initialize server address
    server_addr = ("www.textfiles.com", 80)
    
    # Connect to the server
    try:
        clientSock.connect(server_addr)
        print("Connected to the server...")
    except Exception as e:
        print("connect:", e)
        clientSock.close()
        return

    # Send HEAD request
    request = "GET /art/cowz.txt HTTP/1.1\r\nHost: www.textfiles.com\r\nConnection: close\r\n\r\n"
    clientSock.send(request.encode())
    print(request)
    print("-----------------------------------------------------------")

    # Get the response & print it on the screen
    while True:
        numBytes = int(input("Enter the number of bytes to read: "))

        response = clientSock.recv(numBytes)
        if not response:
            break
        print(response.decode())

    clientSock.close()

if __name__ == "__main__":
    main()
