import socket
import hashlib

def MD5(data):
    if type(data)==bytes:
        return hashlib.md5(data).hexdigest()
    elif type(data)==str:
        return hashlib.md5(data.encode()).hexdigest()
    else:
        return MD5("0")

password = ""           #刷入密码
mnoce = MD5("HelloOTA") #对称验证用，必须32位所以随便MD5一个值就行了
ESP_IP = ""             #ESP8266的IP地址
ESP_UDP_Port = 8266     #ESP8266的OTA端口，默认8266
firmware = "OTA.bin"    #固件文件名
OTA_Port = 8888         #本地端口，用于推送固件数据的TCP端口

# 读固件
firmware_reader = open(firmware,"rb")
firmware_data = firmware_reader.read()
firmware_reader.close()
firmware_md5 = MD5(firmware_data)

# 输出各种参数
print(f"ESP8266 IP:{ESP_IP}\nESP8266 OTA Port:{ESP_UDP_Port}\nFirmware:{firmware}\nFirmware size:{len(firmware_data)}\nFirmware md5:{firmware_md5}")

# 初始化
print("=====================================")
print("Start OTA...")
udp = socket.socket(socket.AF_INET,socket.SOCK_DGRAM)
udp.sendto(f"0 {OTA_Port} {len(firmware_data)} {firmware_md5}".encode(),(ESP_IP,ESP_UDP_Port))
udp.settimeout(10)
try:
    (data,remote) = udp.recvfrom(38)
    if remote[0]==ESP_IP:
        print("AUTH Password")
        auth = data.decode()
        if auth.startswith("AUTH "):
            auth = auth.strip("AUTH ")
            replace_auth = MD5(MD5(password)+":"+auth+":"+mnoce)
            replace_auth = f"200 {mnoce} {replace_auth}"
            udp.sendto(replace_auth.encode(),remote)
            (data,remote) = udp.recvfrom(38)
            if "OK" in data.decode():
                pushTCP = socket.socket(socket.AF_INET,socket.SOCK_STREAM)
                pushTCP.bind(('',OTA_Port))
                pushTCP.listen()
                while True:
                    client,remote = pushTCP.accept()
                    if remote[0] == ESP_IP:
                        client.sendall(firmware_data)
                        while True:
                            data = client.recv(512)
                            print(f"\r{' '*100}\rEPS8266 Receive {data.decode()}",end='')
                            if "OK" in data.decode():
                                print(f"\r{' '*100}\rOK")
                                break
                        client.close()
                        print("OTA Success...")
                        break
                    client.close()
except:
    print("Timeout No Answer.")
    
