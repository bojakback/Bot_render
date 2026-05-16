import time
from datetime import datetime
from threading import Thread
from flask import Flask

# حساب وقت تشغيل السيرفر لأول مرة
START_TIME = datetime.now()

app = Flask("")


@app.route("/")
def home():
    # حساب المدة المستغرقة منذ تشغيل السيرفر وحتى لحظة زيارة الرابط
    uptime = datetime.now() - START_TIME
    days = uptime.days
    hours = uptime.seconds // 3600
    minutes = (uptime.seconds % 3600) // 60
    seconds = uptime.seconds % 60

    output = (
        f"<h1>السيرفر مستيقظ ويعمل بنجاح! 🚀</h1>"
        f"<p>مدة العمل الإجمالية: {days} أيام، و {hours} ساعات، و {minutes} دقائق، و {seconds} ثوانٍ.</p>"
    )
    return output


def run_web_server():
    # تشغيل سيرفر الويب على المنفذ 8080 (أو المنفذ الافتراضي لـ Render)
    app.run(host="0.0.0.0", port=8080)


def keep_alive():
    # تشغيل سيرفر الويب في مسار (Thread) منفصل حتى لا يعطل الحلقة المستمرة
    t = Thread(target=run_web_server)
    t.start()


# 1. تفعيل سيرفر الويب لاستقبال الـ Ping الخارجي
keep_alive()

# 2. الحلقة المستمرة (التي تحسب وتطبع زمن العمل في الـ Logs)
print("تم بدء تشغيل العداد والحلقة المستمرة...")
while True:
    current_uptime = datetime.now() - START_TIME
    print(f"[سجل العمل] السيرفر يعمل منذ: {current_uptime}", flush=True)

    # يطبع في السجلات كل 60 ثانية (يمكنك تغييرها كما تحب)
    time.sleep(60)
