import socket

def get_local_ip():
    s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    try:
        # doesn't even have to be reachable
        s.connect(('8.8.8.8', 1))
        IP = s.getsockname()[0]
    except Exception:
        IP = '127.0.0.1'
    finally:
        s.close()
    return IP

if __name__ == "__main__":
    ip = get_local_ip()
    print("\n" + "="*40)
    print("      FEDORA FEDERATED HOST")
    print("="*40)
    print(f"\nLocal Network URL: http://{ip}:8000/")
    print("\nOther devices on your Wi-Fi can join at this URL.")
    print("="*40 + "\n")
