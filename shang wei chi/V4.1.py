import tkinter as tk
from tkinter import ttk
import socket
import re
import csv
import threading
from datetime import datetime
import matplotlib.pyplot as plt
from matplotlib.backends.backend_tkagg import FigureCanvasTkAgg


class AirQualityApp:
    def __init__(self, master):
        self.master = master
        master.title('空气质量检测无人机的设计与实现 2021040714')
        master.protocol('WM_DELETE_WINDOW', self.on_close)  # 添加关闭事件绑定
        master.configure(bg='white')  # 设置窗口背景为白色
        
        # 连接状态指示
        self.status_label = tk.Label(master, text="连接状态: 未连接", fg='red', bg='white')
        self.status_label.pack(pady=5)

        # 数据显示区域
        data_frame = tk.Frame(master, bg='white')
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
            frame = tk.Frame(data_frame, bg='white')
            frame.grid(row=0, column=i, padx=10)
            
            label = tk.Label(frame, text=param.upper(), font=('Arial', 12), bg='white')
            label.pack()
            
            value_label = tk.Label(frame, text='--', font=('Arial', 24), bg='white')
            value_label.pack()
            
            unit_label = tk.Label(frame, text=info['unit'], bg='white')
            unit_label.pack()
            
            self.labels[param] = {'value': value_label, 'unit': unit_label}

        # 添加分析文本框
        self.analysis_label = tk.Label(master, text='智能分析:', anchor='w', bg='white')
        self.analysis_label.pack(side=tk.TOP, fill=tk.X, padx=10, pady=(5,0))
        
        self.analysis_text = tk.Text(master, height=6, state='disabled', bg='white')
        self.analysis_text.pack(side=tk.TOP, fill=tk.BOTH, padx=10, pady=(0,5))

        # 控制按钮区域
        control_frame = tk.Frame(master, bg='white')
        control_frame.pack(side=tk.BOTTOM, pady=5)
        
        style = ttk.Style()
        style.configure('Rounded.TButton', borderwidth=0, relief='flat', padding=6, background='#f0f0f0', foreground='black')
        style.map('Rounded.TButton', background=[('active', '#e0e0e0')])
        
        self.export_btn = ttk.Button(control_frame, text="导出数据", command=self.export_data, style='Rounded.TButton')
        self.export_btn.pack(side=tk.LEFT, padx=20)
        
        self.export_chart_btn = ttk.Button(control_frame, text="导出图表", command=self.save_chart, style='Rounded.TButton')
        self.export_chart_btn.pack(side=tk.LEFT, padx=20)
        

        
        # 数据存储
        from datetime import datetime
        self.history = {param: [] for param in self.params}
        self.timestamps = []
        self.data_buffer = []
        self.last_save = datetime.now()
        
        # 网络配置
        self.host = '192.168.4.1'
        self.port = 8080
        self.running = True
        self.connect()

    def update_display(self, param, value, is_warning):
        # 更新参数字典
        self.params[param]['value'] = value
        
        label_info = self.labels[param]
        label_info['value'].config(text=f'{value:.2f}', 
                                  bg='#ffcccc' if is_warning else 'white')
        
        # 更新带时间戳的数据
        timestamp = datetime.now().strftime('%Y-%m-%d %H:%M:%S.%f')[:-3]
        
        # 限制历史数据存储数量
        MAX_HISTORY = 30  # 减少历史数据点数量
        
        # 更新历史数据
        self.history[param].append(value)
        if len(self.history[param]) > MAX_HISTORY:
            self.history[param].pop(0)
        
        # 更新时间戳
        self.timestamps.append(timestamp)
        if len(self.timestamps) > MAX_HISTORY:
            self.timestamps.pop(0)
        
        # 缓存数据准备写入
        self.data_buffer.append({
            'timestamp': timestamp,
            'param': param,
            'value': value,
            'warning': is_warning
        })
        
        # 每60秒自动保存
        if (datetime.now() - self.last_save).total_seconds() > 60:
            self.save_to_csv()
        
        # 触发分析更新
        analysis_result = self.analyze_data()
        self.analysis_text.config(state='normal')
        self.analysis_text.delete(1.0, tk.END)
        self.analysis_text.insert(tk.END, analysis_result)
        self.analysis_text.config(state='disabled')
        
        # 优化图表更新频率 - 每5次数据更新才重绘一次
        if len(self.history[param]) % 5 == 0:
            self.update_chart()
     #这段代码定义了一个名为 connect 的方法，用于通过 TCP 协议连接到服务器。
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
        self.raw_data_label = tk.Label(self.master, text='原始数据:', anchor='w', bg='white')
        self.raw_data_label.pack(side=tk.TOP, fill=tk.X, padx=10)
        self.raw_text = tk.Text(self.master, height=4, state='disabled', bg='white')
        self.raw_text.pack(side=tk.TOP, fill=tk.X, padx=10, pady=5)
        
        # 添加图表区域
        self.figure = plt.Figure(figsize=(8, 4), dpi=100)
        self.canvas = FigureCanvasTkAgg(self.figure, master=self.master)
        self.canvas.get_tk_widget().pack(side=tk.TOP, fill=tk.BOTH, expand=True, padx=10, pady=5)
        self.ax = self.figure.add_subplot(111)
        
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

    def save_to_csv(self):
        """保存数据到CSV文件"""
        try:
            import os
            save_dir = os.path.join(os.path.expanduser('~'), 'AirQualityData')
            os.makedirs(save_dir, exist_ok=True)
            file_path = os.path.join(save_dir, 'air_quality_data.csv')
            
            with open(file_path, 'a', newline='', encoding='utf-8-sig') as f:
                writer = csv.writer(f)
                if f.tell() == 0:
                    writer.writerow(['时间戳', '参数', '数值', '预警状态'])
                for record in self.data_buffer:
                    writer.writerow([
                        record['timestamp'],
                        record['param'],
                        record['value'],
                        '是' if record['warning'] else '否'
                    ])
                self.data_buffer.clear()
                self.last_save = datetime.now()
        except PermissionError:
            print(f'权限错误：请关闭正在使用的文件 {file_path}')
        except Exception as e:
            print(f'数据保存失败: {str(e)}')

    def export_data(self):
        """手动触发数据导出"""
        self.save_to_csv()
        
    def save_chart(self):
        """保存当前图表为PNG文件"""
        try:
            import os
            save_dir = os.path.join(os.path.expanduser('~'), 'AirQualityData')
            os.makedirs(save_dir, exist_ok=True)
            file_path = os.path.join(save_dir, 'air_quality_chart.png')
            self.figure.savefig(file_path, dpi=100)
            print(f'图表已保存到: {file_path}')
        except Exception as e:
            print(f'图表保存失败: {str(e)}')

    def on_close(self):
        """窗口关闭事件处理"""
        self.running = False  # 停止数据接收线程
        if hasattr(self, 'client_socket'):
            self.client_socket.close()  # 关闭socket连接
        self.master.destroy()  # 销毁主窗口

    def calculate_aqi(self, pm25, co):
        """计算AQI指数"""
        # AQI计算标准 (PM2.5: μg/m³, CO: ppm)
        aqi_pm25 = min(max(0, (pm25 / 35) * 100), 500)  # PM2.5占比
        aqi_co = min(max(0, (co / 9) * 100), 500)       # CO占比
        aqi = max(aqi_pm25, aqi_co)                     # 取最大值作为AQI
        
        # AQI等级评价
        if aqi <= 50:
            return aqi, "优", "空气质量令人满意，基本无空气污染"
        elif aqi <= 100:
            return aqi, "良", "空气质量可接受，但某些污染物可能对极少数异常敏感人群健康有较弱影响"
        elif aqi <= 150:
            return aqi, "轻度污染", "易感人群症状有轻度加剧，健康人群出现刺激症状"
        elif aqi <= 200:
            return aqi, "中度污染", "进一步加剧易感人群症状，可能对健康人群心脏、呼吸系统有影响"
        elif aqi <= 300:
            return aqi, "重度污染", "心脏病和肺病患者症状显著加剧，运动耐受力降低，健康人群普遍出现症状"
        else:
            return aqi, "严重污染", "健康人群运动耐受力降低，有明显强烈症状，提前出现某些疾病"

    def update_chart(self):
        """更新图表显示"""
        self.ax.clear()
        
        colors = ['b', 'g', 'r', 'c', 'm']
        for i, (param, values) in enumerate(self.history.items()):
            if len(values) > 0:
                self.ax.plot(values, label=param.upper(), color=colors[i])
        
        self.ax.legend(loc='upper right')
        self.ax.set_xlabel('time')
        self.ax.set_ylabel('value')
        self.ax.set_title('Air Quality Chart')
        self.ax.grid(True)
        self.canvas.draw()
        
    def analyze_data(self):
        analysis = []
        thresholds = {
            'temp': {'min': 18, 'max': 28},
            'humi': {'min': 40, 'max': 70},
            'pm2.5': {'max': 35},
            'ch2o': {'max': 0.08},
            'co': {'max': 9}
        }
        
        # 计算AQI指数
        pm25 = self.params['pm2.5']['value']
        co = self.params['co']['value']
        aqi, level, suggestion = self.calculate_aqi(pm25, co)
        analysis.append(f"AQI指数: {aqi:.0f} ({level})")
        analysis.append(f"健康建议: {suggestion}")
        
        # 其他参数检查
        for param, value in self.params.items():
            current = value['value']
            if param in thresholds:
                if current < thresholds[param].get('min', float('-inf')):
                    analysis.append(f"{param.upper()}过低 ({current}{self.params[param]['unit']})")
                elif current > thresholds[param].get('max', float('inf')):
                    analysis.append(f"{param.upper()}超标 ({current}{self.params[param]['unit']})")
        
        return '\n'.join(analysis) if analysis else "所有参数均在安全范围内"

if __name__ == '__main__':
    root = tk.Tk()
    app = AirQualityApp(root)
    root.mainloop()