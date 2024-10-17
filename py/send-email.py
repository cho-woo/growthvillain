import cgi
import smtplib
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart

# 이메일 설정
smtp_server = 'smtp.gmail.com'
smtp_port = 587
your_email = 'hi341096@gmail.com'  # 본인의 구글 이메일 주소
your_password = 'jflnrmnsrxhtlmtm'   # 앱 비밀번호 (구글 계정 보안을 위해 앱 비밀번호 사용)

# CGI로 데이터 받기
form = cgi.FieldStorage()
company = form.getvalue('company')
email = form.getvalue('email')
phone = form.getvalue('phone')
source = form.getvalue('source')
topic = form.getvalue('topic')
message = form.getvalue('message')

# 이메일 내용 설정
msg = MIMEMultipart()
msg['From'] = your_email
msg['To'] = your_email
msg['Subject'] = f"문의가 접수되었습니다: {topic}"

body = f"""
회사/단체명: {company}
이메일: {email}
전화번호: {phone}
어디서 알게 되었나요?: {source}
문의 주제: {topic}
내용:
{message}
"""
msg.attach(MIMEText(body, 'plain'))

# 이메일 전송
try:
    server = smtplib.SMTP(smtp_server, smtp_port)
    server.starttls()  # TLS 암호화 시작
    server.login(your_email, your_password)
    server.send_message(msg)
    server.quit()
    print("Content-Type: text/html\n")
    print("<html><body><h2>문의가 성공적으로 전송되었습니다.</h2></body></html>")
except Exception as e:
    print("Content-Type: text/html\n")
    print(f"<html><body><h2>문의 전송에 실패했습니다: {e}</h2></body></html>")
