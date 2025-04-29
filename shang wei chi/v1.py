import tkinter as tk
import socket
import re
import threading
from matplotlib.backends.backend_tkagg import FigureCanvasTkAgg
import matplotlib.pyplot as plt
from matplotlib.animation import FuncAnimation

class AirQualityApp:
    def __init__(self, master):
        self.master = master
        master.title('空气质量监测系统')
        master.protocol('WM_DELETE_WINDOW', self.on_close)  # 添加关闭事件绑定
        
        # 连接状态指示
        self.status_label = tk.Label(master, text="连接状态: 未连接", fg='red')
        self.status_label.pack(pady=5)

        # 数据显示区域
        data_frame = tk.Frame(master)
        data_frame.pack(pady=10)
        
        self.params = {
            'temp': {'unit': '°C', 'value': 0.0},
            'humi': {'unit': '%', 'value': 0.0},
            'ch2o': {'unit': 'mg/m³', 'value': 0.0},
            'pm2.5': {'unit': 'μg/m³', 'value': 0},
            'co': {'unit': 'ppm', 'value': 0}
        }
        
        self.labels = {}
        for i, (param, info) in enumerate(self.params.items()):
            frame = tk.Frame(data_frame)
            frame.grid(row=0, column=i, padx=10)
            
            label = tk.Label(frame, text=param.upper(), font=('Arial', 12))
            label.pack()
            
            value_label = tk.Label(frame, text='--', font=('Arial', 24))
            value_label.pack()
            
            unit_label = tk.Label(frame, text=info['unit'])
            unit_label.pack()
            
            self.labels[param] = {'value': value_label, 'unit': unit_label}

        # 图表区域
        fig, self.ax = plt.subplots(figsize=(8, 4))
        self.lines = {param: self.ax.plot([], [], label=param.upper())[0] for param in self.params}
        self.ax.legend()
        self.ax.set_xlabel('时间')
        self.ax.set_ylabel('数值')
        
        self.canvas = FigureCanvasTkAgg(fig, master=master)
        self.canvas.get_tk_widget().pack(side=tk.BOTTOM, fill=tk.BOTH, expand=True)
        
        # 数据存储
        self.history = {param: [] for param in self.params}
        self.timestamps = []
        
        # 网络配置
        self.host = '192.168.4.1'
        self.port = 8080
        self.running = True
        self.connect()

    def update_display(self, param, value, is_warning):
        label_info = self.labels[param]
        label_info['value'].config(text=f'{value:.2f}', 
                                  bg='#ffcccc' if is_warning else 'white')
        
        # 更新历史数据
        self.history[param].append(value)
        self.timestamps.append(len(self.timestamps))
        
        # 保持最近60个数据点
        if len(self.timestamps) > 60:
            self.timestamps.pop(0)
            for p in self.params:
                if len(self.history[p]) > 60:
                    self.history[p].pop(0)
        
        # 更新图表
        for param, line in self.lines.items():
            line.set_data(self.timestamps, self.history[param])
        self.ax.relim()
        self.ax.autoscale_view()
        self.canvas.draw()

    def connect(self):
        self.client_socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        self.client_socket.settimeout(5)
        try:
            self.client_socket.connect((self.host, self.port))
            self.status_label.config(text="连接状态: 已连接", fg='green')
            threading.Thread(target=self.receive_data, daemon=True).start()
        except Exception as e:
            self.status_label.config(text=f"连接失败: {str(e)}", fg='red')
            self.master.after(5000, self.connect)

    def receive_data(self):
        buffer = ''
        pattern = re.compile(r'(\w+_warn)?\$((?:pm2\.5|[a-z0-9]+)):([+-]?\d+\.?\d*)#')
        # 初始化原始数据显示组件
        self.raw_data_label = tk.Label(self.master, text='原始数据:', anchor='w')
        self.raw_data_label.pack(side=tk.TOP, fill=tk.X, padx=10)
        self.raw_text = tk.Text(self.master, height=4, state='disabled')
        self.raw_text.pack(side=tk.TOP, fill=tk.X, padx=10, pady=5)
        
        while self.running:
            try:
                data = self.client_socket.recv(1024).decode('utf-8', errors='ignore')
                print('接收原始数据:', data)  # 调试输出移至此处
                self.raw_text.config(state='normal')
                self.raw_text.insert(tk.END, data)
                self.raw_text.see(tk.END)
                self.raw_text.config(state='disabled')
                self.raw_text.update_idletasks()
                if not data:
                    raise ConnectionError("连接已关闭")
                
                buffer += data
                # 按字段分割处理
                for segment in buffer.split(','):
                    match = pattern.match(segment.strip())
                    if match:
                        prefix, param, value = match.groups()
                        is_warning = bool(prefix)
                        print(f'解析到字段: {segment} => {param}={value} (警告: {is_warning})')  # 增强调试信息
                        
                        # 数值转换
                        try:
                            numeric_value = float(value) if '.' in value else int(value)
                            self.master.after(0, self.update_display, param, numeric_value, is_warning)
                        except ValueError as ve:
                            print(f'数值转换错误: {value} => {ve}')
                        
                        # 清空已处理缓冲区
                        # 保留未解析内容用于下次匹配
                        buffer = buffer[len(segment):] if segment in buffer else ''
                    else:
                        print(f'未匹配字段: {segment}')  # 显示未解析内容
                
            except Exception as e:
                self.status_label.config(text=f"连接错误: {str(e)}", fg='red')
                self.master.after(5000, self.connect)
                break

    def on_close(self):
        """窗口关闭事件处理"""
        self.running = False  # 停止数据接收线程
        if hasattr(self, 'client_socket'):
            self.client_socket.close()  # 关闭socket连接
        self.master.destroy()  # 销毁主窗口

if __name__ == '__main__':
    root = tk.Tk()
    app = AirQualityApp(root)
    root.mainloop()