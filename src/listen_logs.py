import socket

# Слушаем порт 9999 на ВСЕХ интерфейсах (включая Tailscale)
UDP_PORT = 9999

sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
sock.bind(("0.0.0.0", UDP_PORT))

print(f"🟢 Слушаю UDP порт {UDP_PORT} от Raspberry через Tailscale...")
print("Нажмите Ctrl+C для выхода.\n")

try:
    while True:
        data, addr = sock.recvfrom(1024)
        message = data.decode('utf-8', errors='ignore').strip()
        print(f"[{addr[0]}:{addr[1]}] {message}")
except KeyboardInterrupt:
    print("\n🔴 Слушатель остановлен.")