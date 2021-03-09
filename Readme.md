# 什么是ArduinoOTA
ArduinoOTA 库是一个库，它允许无线 Wi-Fi 更新 Arduino 程序（以及 ESP8226、ESP32）。开发连接对象时，它是一个基本库。它允许更新程序，而无需拆卸微控制器（Arduino，ESP8266，ESP32）将其连接到他的电脑。 这个库最初是为了更新 Arduino 程序而开发的，ESP8266 和 ESP32 是完全支持的。
#### 优势
可以不需要通过USB串口线为ESP8266等设备下载程序
#### 缺陷
目前使用下来发现有时候无法通过mDNS发现到设备(可能是被防火墙拦截了)
## 通过分析ArduinoOTA源码用脚本实现与ESP通讯直接下载

```c
if (_state == OTA_IDLE) {					//如果状态为等待状态开始通讯
    int cmd = parseInt();					//通过UDP获取一个int数据作为tag
    if (cmd != U_FLASH && cmd != U_FS)		//判断tag是否为U_FLASH或者U_FS
      return;
    _ota_ip = _udp_ota->getRemoteAddress();	//成功认证tag为U_FLAS或U_FS后保存UDP远端的IP
    _cmd  = cmd;							//复制cmd tag
    _ota_port = parseInt();					//再从UDP获取一个int类型数据作为下载时的远程端口
    _ota_udp_port = _udp_ota->getRemotePort();
    _size = parseInt();						//获取下载固件的大小
    _udp_ota->read();
    _md5 = readStringUntil('\n');			//获取下载固件MD5校验值
    _md5.trim();
    if(_md5.length() != 32)
      return;

    ota_ip = _ota_ip;						//复制远程IP

    if (_password.length()){				//从这里开始生成一个ESP端加密 盐
      MD5Builder nonce_md5;
      nonce_md5.begin();
      nonce_md5.add(String(micros()));
      nonce_md5.calculate();
      _nonce = nonce_md5.toString();

      char auth_req[38];
      sprintf(auth_req, "AUTH %s", _nonce.c_str());
      _udp_ota->append((const char *)auth_req, strlen(auth_req));
      _udp_ota->send(ota_ip, _ota_udp_port);//将加密盐发送至固件上传端
      _state = OTA_WAITAUTH;				//改变当前的状态为等待验证
      return;
    } else {
      _state = OTA_RUNUPDATE;				//改变当前的状态为开始更新
    }
  } else if (_state == OTA_WAITAUTH) {		//认证状态开始认证密码
    int cmd = parseInt();					//获取一个int数据作为tag
    if (cmd != U_AUTH) {					//如果tag不是U_AUTH则退出
      _state = OTA_IDLE;
      return;
    }
    _udp_ota->read();
    String cnonce = readStringUntil(' ');	//获取上传端的加密 盐
    String response = readStringUntil('\n');//获取加密后的密码
    if (cnonce.length() != 32 || response.length() != 32) {
      _state = OTA_IDLE;
      return;
    }

    String challenge = _password + ':' + String(_nonce) + ':' + cnonce;//用本地保存的密码构建加密密码验证上传端密码是否正确
    MD5Builder _challengemd5;
    _challengemd5.begin();
    _challengemd5.add(challenge);
    _challengemd5.calculate();			//MD5加密本地构建的密码
    String result = _challengemd5.toString();

    ota_ip = _ota_ip;
    if(result.equalsConstantTime(response)) {	//如果密码正确则将状态改为上传状态
      _state = OTA_RUNUPDATE;
    } else {
      _udp_ota->append("Authentication Failed", 21);
      _udp_ota->send(ota_ip, _ota_udp_port);
      if (_error_callback) _error_callback(OTA_AUTH_ERROR);
      _state = OTA_IDLE;
    }
  }

  while(_udp_ota->next()) _udp_ota->flush();
```
下面是上传数据代码

```c

WiFiClient client;
client.connect(_ota_ip, _ota_port)		//连接远程上传主机
written = Update.write(client);			//将获取的数据传入Update
if (written > 0) {
   client.print(written, DEC);			//返回获取数据长度
   total += written;
   if(_progress_callback) {
     _progress_callback(total, _size);
   }
}
if (Update.end()) {						//如果数据获取完毕刷入
// Ensure last count packet has been sent out and not combined with the final OK
	client.flush();
	delay(1000);
	client.print("OK");					//返回OK给远程上传主机
	client.flush();
	delay(1000);
	client.stop();						//断开连接
	#ifdef OTA_DEBUG
	OTA_DEBUG.printf("Update Success\n");
	#endif
	if (_end_callback) {
	  _end_callback();
	}
	if(_rebootOnSuccess){
	#ifdef OTA_DEBUG
	OTA_DEBUG.printf("Rebooting...\n");
	#endif
	  //let serial/network finish tasks that might be given in _end_callback
	  delay(100);
	  ESP.restart();
}
```
总结一下大概是这样的

```c
/*
===========================UDP==============================
|上传主机|  "U_FLASH Port MD5"-UDP发送至8266端口-> |ESP8266/32|
|上传主机|    <-UDP-- "AUTH {32位的加密盐A}"----   |ESP8266/32|
|上传主机|  "U_AUTH {32位加密盐B} {加密后的密码}"->  |ESP8266/32|
|上传主机|              <--"OK"---                |ESP8266/32|
============================================================
然后上传主机开启一个TCP端口位上面的Port的Socket
ESP8266/32连接到TCP端口后上传主机将固件发送至ESP8266/32
*/
```
通过Python实现上面的通讯协议后可以直接与ESP8266/32通讯并上传固件

```python
import socket
import hashlib

def MD5(data):
    if type(data)==bytes:
        return hashlib.md5(data).hexdigest()
    elif type(data)==str:
        return hashlib.md5(data.encode()).hexdigest()
    else:
        return MD5("0")

password = "" 			#刷入密码
mnoce = MD5("HelloOTA") #对称验证用，必须32位所以随便MD5一个值就行了
ESP_IP = "192.168.1.1"  #ESP8266的IP地址
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
```
脚本下载链接 [ArduinoOTA-Client](https://github.com/GuokeNo1/ArduinoOTA-Client)