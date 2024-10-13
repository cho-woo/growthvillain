import smtplib
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
import cgi

# 폼 데이터 가져오기
form = cgi.FieldStorage()
company = form.getvalue('company')
email = form.getvalue('email')
phone = form.getvalue('phone')
source = form.getvalue('source')
topic = form.getvalue('topic')
message = form.getvalue('message')

# 이메일 설정
sender_email = "hi341096@gmail.com"  # 발신자 이메일
receiver_email = "your_email@gmail.com"  # 수신자 이메일
password = "dkrakdi018!"  # 발신자 이메일 비밀번호

# 이메일 내용 설정
msg = MIMEMultipart()
msg['From'] = sender_email
msg['To'] = receiver_email
msg['Subject'] = f"Contact Inquiry from {company}"

# 이메일 본문
body = f"""
회사/단체명: {company}
이메일: {email}
전화번호: {phone}
어떻게 알게 되셨나요?: {source}
관심/문의 주제: {topic}
문의사항: {message}
"""

msg.attach(MIMEText(body, 'plain'))

# SMTP 서버에 연결하여 이메일 보내기
try:
    with smtplib.SMTP('smtp.gmail.com', 587) as server:
        server.starttls()
        server.login(sender_email, password)
        server.send_message(msg)
    print("Content-type: text/html\n")
    print("<html><body><h1>이메일이 성공적으로 전송되었습니다.</h1></body></html>")
except Exception as e:
    print("Content-type: text/html\n")
    print(f"<html><body><h1>이메일 전송 실패: {e}</h1></body></html>")
