# ==========================================
# 1. استدعاء المكتبات (شاملة مكتبات البوت والويب)
# ==========================================
import asyncio
import aiohttp
import json
import time
import math
from collections import deque
from datetime import datetime
import logging
from threading import Thread
from flask import Flask
from Orders import oco

# ==========================================
# 2. إعدادات خادم الويب (Keep-Alive) لإبقاء السيرفر مستيقظاً
# ==========================================
START_TIME = datetime.now()
app = Flask("")

@app.route("/")
def home():
    uptime = datetime.now() - START_TIME
    days = uptime.days
    hours = uptime.seconds // 3600
    minutes = (uptime.seconds % 3600) // 60
    seconds = uptime.seconds % 60
    return (
        f"<h1>بوت التداول يعمل بكفاءة! 🚀</h1>"
        f"<p>مدة العمل المتواصلة: {days} أيام، {hours} ساعات، {minutes} دقائق، {seconds} ثوانٍ.</p>"
    )

def run_web_server():
    log = logging.getLogger('werkzeug')
    log.setLevel(logging.ERROR)
    app.run(host="0.0.0.0", port=8080)

def keep_alive():
    t = Thread(target=run_web_server)
    t.start()


# ==========================================
# 3. كود بوت التداول
# ==========================================

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s | %(levelname)s | %(message)s',
    datefmt='%H:%M:%S'
)
log = logging.getLogger(__name__)

# ══════════════════════════════════════════════════════════════
#  ⚙️  إعدادات المستخدم – عدّل هنا فقط
# ══════════════════════════════════════════════════════════════
TELEGRAM_TOKEN   = "8920750196:AAEBROUxyPeByMgPOo2zj5XEObryoMzdQ5o"
TELEGRAM_CHAT_ID = "8561627376"

SYMBOLS = ["AIXBTUSDT","CFGUSDT","CHIPUSDT","COWUSDT","CRVUSDT","DOLOUSDT","ESPUSDT","ETHFIUSDT","ETHUSDT","EULUSDT","GIGGLEUSDT","HEMIUSDT","HOMEUSDT","KAITOUSDT","LAUSDT","METUSDT","MMTUSDT","NEWTUSDT","OPNUSDT","PLUMEUSDT","QNTUSDT	","ROBOUSDT","SFPUSDT","TURTLEUSDT","WLFIUSDT","XPLUSDT","ZBTUSDT","WBETHUSDT","SOLVUSDT",]

#["ZBTUSDT","ZAMAUSDT","WBETHUSDT","ETHUSDT","LAUSDT","BTCUSDT","MEMEUSDT","SOLVUSDT",]
#["AIXBTUSDT","CFGUSDT","CHIPUSDT","COWUSDT","CRVUSDT","DOLOUSDT","ESPUSDT","ETHFIUSDT","ETHUSDT","EULUSDT","GIGGLEUSDT","HEMIUSDT","HOMEUSDT","KAITOUSDT","LAUSDT","METUSDT","MMTUSDT","NEWTUSDT","OPNUSDT","PLUMEUSDT","QNTUSDT	","ROBOUSDT","SFPUSDT","TURTLEUSDT","WLFIUSDT","XPLUSDT","ZBTUSDT","WBETHUSDT","SOLVUSDT",]
#'ZAMAUSDT',ACX

CAPITAL_PER_SYMBOL = 100.0   # رأس المال لكل عملة بالدولار
TIMEFRAME          = "1h"    # الإطار الزمني
COMMISSION         = 0.001   # 0.1% عمولة بينانس
PERIOD             = 2       # فترة الفراكتال

# ──────────────────────────────────────────────────────────────
#  🎯 إعدادات TP و SL
#  ضع نسبة مئوية (مثال: 0.012 = 1.2%) أو اكتب None للاستخدام الافتراضي
#
#  TP_FIXED_PCT:
#    - رقم  → TP ثابت بهذه النسبة من سعر الدخول
#    - None → TP يُحسب من المسافة للـ SL (الطريقة القديمة: risk * TP_RATIO)
#
#  SL_FIXED_PCT:
#    - رقم  → SL ثابت بهذه النسبة أسفل سعر الدخول
#    - None → SL يُحسب من آخر فراكتال دعم (الطريقة القديمة)
# ──────────────────────────────────────────────────────────────
TP_FIXED_PCT  = 0.7   # مثال: 0.012 = 1.2% | None = فراكتال
SL_FIXED_PCT  = None    # مثال: 0.010 = 1.0% | None = فراكتال
TP_RATIO      = 1.0     # يُستخدم فقط إذا كان TP_FIXED_PCT = None

# فلاتر الاختراق الكاذب
VOLUME_MULTIPLIER  = 1.5
VOLUME_LOOKBACK    = 20
ATR_PERIOD         = 14
MAX_ATR_MULTIPLIER = 3.0
RSI_PERIOD         = 14
RSI_OVERBOUGHT     = 72
MAX_WICK_RATIO     = 0.6

# عدد الشموع التاريخية عند البدء
HISTORICAL_CANDLES = 720

# ══════════════════════════════════════════════════════════════
#  Telegram
# ══════════════════════════════════════════════════════════════
class TelegramBot:
    def __init__(self, token, chat_id):
        self.token   = token
        self.chat_id = chat_id
        self.url     = f"https://api.telegram.org/bot{token}/sendMessage"
        self._queue  = asyncio.Queue()

    async def send(self, text: str, parse_mode="HTML"):
        await self._queue.put((text, parse_mode))

    async def _worker(self):
        async with aiohttp.ClientSession() as session:
            while True:
                text, parse_mode = await self._queue.get()
                try:
                    payload = {
                        "chat_id":    self.chat_id,
                        "text":       text,
                        "parse_mode": parse_mode,
                    }
                    async with session.post(self.url, json=payload) as r:
                        if r.status != 200:
                            body = await r.text()
                            log.warning(f"Telegram error {r.status}: {body}")
                except Exception as e:
                    log.error(f"Telegram send failed: {e}")
                finally:
                    await asyncio.sleep(0.4)
                    self._queue.task_done()

    def start(self, loop):
        loop.create_task(self._worker())

# ══════════════════════════════════════════════════════════════
#  Message Templates
# ══════════════════════════════════════════════════════════════
def msg_open_trade(symbol, entry, sl, tp, equity, risk_usd):
    es = None
    current_bot_ip = "غير متاح"
    try:
        import requests
        current_bot_ip = requests.get('https://api.ipify.org', timeout=10).text
        print("\n" + "="*40)
        print(f"🤖 عنوان الـ IP الحالي للبوت هو: {current_bot_ip}")
        print("="*40 + "\n")
    except Exception as e:
        print(f"❌ فشل استخراج الـ IP بسبب: {e}")
    try:
        es = oco(symbol, tp, sl)
        oco_status = "OK"
        oco_entry  = es
        oco_error  = ""
    except Exception as e:
        oco_status = "FAILED"
        oco_entry  = ""
        oco_error  = str(e)
    sl_pct  = abs(entry - sl) / entry * 100
    tp_pct  = abs(tp - entry) / entry * 100
    sl_mode = f"ثابت {SL_FIXED_PCT*100:.1f}%" if SL_FIXED_PCT is not None else "فراكتال"
    tp_mode = f"ثابت {TP_FIXED_PCT*100:.1f}%" if TP_FIXED_PCT is not None else f"فراكتال ×{TP_RATIO}"
    return (
        f"🧠 OCO: {oco_status}\n"
        f"💰 Entry: {oco_entry}\n"
        f"⚠️ Error: {oco_error}\n"
        f"IP: {current_bot_ip}\n"
        f"🟢 <b>صفقة جديدة مفتوحة</b>\n"
        f"{'─'*20}\n"
        f"📌 العملة:      <b>{symbol}</b>\n"
        f"Entery: <code>{entry:.4f}</code>\n"
        f"🛑SL: <code>{sl:.4f}</code>  (-{sl_pct:.2f}%)  [{sl_mode}]\n"
        f"🎯TP:  <code>{tp:.4f}</code>  (+{tp_pct:.2f}%)  [{tp_mode}]\n"
        f"💰 رأس المال:   <code>${equity:,.2f}</code>\n"
        f"⚠️ مخاطرة:     <code>${risk_usd:.2f}</code>\n"
        f"🕐 {datetime.now().strftime('%Y-%m-%d %H:%M')}"
    )

def msg_close_win(symbol, entry, exit_p, pnl_usd, pnl_pct, equity, wins, losses):
    wr = wins / (wins + losses) * 100 if (wins + losses) > 0 else 0
    return (
        f"✅ <b>صفقة رابحة</b>\n"
        f"{'─'*28}\n"
        f"📌 العملة:      <b>{symbol}</b>\n"
        f"💵 دخول:       <code>{entry:.4f}</code>\n"
        f"💵 خروج:       <code>{exit_p:.4f}</code>\n"
        f"📈 الربح:      <b>+${pnl_usd:.2f}  (+{pnl_pct:.2f}%)</b>\n"
        f"{'─'*28}\n"
        f"💼 الرصيد الحالي: <code>${equity:,.2f}</code>\n"
        f"📊 الإجمالي:  {wins}✅ {losses}❌  |  WR: {wr:.1f}%\n"
        f"🕐 {datetime.now().strftime('%Y-%m-%d %H:%M')}"
    )

def msg_close_loss(symbol, entry, exit_p, pnl_usd, pnl_pct, equity, wins, losses):
    wr = wins / (wins + losses) * 100 if (wins + losses) > 0 else 0
    return (
        f"❌ <b>صفقة خاسرة</b>\n"
        f"{'─'*28}\n"
        f"📌 العملة:      <b>{symbol}</b>\n"
        f"💵 دخول:       <code>{entry:.4f}</code>\n"
        f"💵 خروج:       <code>{exit_p:.4f}</code>\n"
        f"📉 الخسارة:    <b>-${abs(pnl_usd):.2f}  (-{abs(pnl_pct):.2f}%)</b>\n"
        f"{'─'*28}\n"
        f"💼 الرصيد الحالي: <code>${equity:,.2f}</code>\n"
        f"📊 الإجمالي:  {wins}✅ {losses}❌  |  WR: {wr:.1f}%\n"
        f"🕐 {datetime.now().strftime('%Y-%m-%d %H:%M')}"
    )

def msg_rejected(symbol, reason):
    return (
        f"🚫 <b>إشارة مرفوضة</b> | <b>{symbol}</b>\n"
        f"السبب: {reason}"
    )

def msg_daily_stats(records):
    lines = [f"📊 <b>تقرير يومي – {datetime.now().strftime('%Y-%m-%d')}</b>\n{'═'*28}"]
    total_trades = total_wins = total_losses = 0
    total_pnl = 0.0
    for r in records:
        sym    = r['symbol']
        trades = r['wins'] + r['losses']
        wr     = r['wins'] / trades * 100 if trades else 0
        pnl    = r['equity'] - CAPITAL_PER_SYMBOL
        emoji  = "🟢" if pnl >= 0 else "🔴"
        lines.append(
            f"{emoji} <b>{sym}</b>:  {trades} صفقة  |  WR {wr:.0f}%  |  "
            f"{'+'if pnl>=0 else ''}{pnl:.2f}$"
        )
        total_trades += trades
        total_wins   += r['wins']
        total_losses += r['losses']
        total_pnl    += pnl
    overall_wr = total_wins / total_trades * 100 if total_trades else 0
    lines.append(f"{'─'*28}")
    lines.append(
        f"🏁 <b>المجموع:</b> {total_trades} صفقة  |  WR {overall_wr:.1f}%  |  "
        f"{'+'if total_pnl>=0 else ''}{total_pnl:.2f}$"
    )
    return "\n".join(lines)

def msg_historical_report(records):
    """تقرير ما بعد تحميل البيانات التاريخية"""
    lines = [f"📋 <b>تقرير البيانات التاريخية – {datetime.now().strftime('%Y-%m-%d %H:%M')}</b>\n{'═'*28}"]
    total_trades = total_wins = total_losses = 0
    total_pnl = 0.0
    for r in records:
        sym    = r['symbol']
        trades = r['wins'] + r['losses']
        wr     = r['wins'] / trades * 100 if trades else 0
        pnl    = r['equity'] - CAPITAL_PER_SYMBOL
        emoji  = "🟢" if pnl >= 0 else "🔴"
        dd_str = f"  |  DD {r['max_dd']:.1f}%" if r['max_dd'] > 0 else ""
        lines.append(
            f"{emoji} <b>{sym}</b>:  {trades} صفقة  |  WR {wr:.0f}%  |  "
            f"{'+'if pnl>=0 else ''}{pnl:.2f}${dd_str}"
        )
        total_trades += trades
        total_wins   += r['wins']
        total_losses += r['losses']
        total_pnl    += pnl
    overall_wr = total_wins / total_trades * 100 if total_trades else 0
    lines.append(f"{'─'*28}")
    lines.append(
        f"🏁 <b>المجموع:</b> {total_trades} صفقة  |  WR {overall_wr:.1f}%  |  "
        f"{'+'if total_pnl>=0 else ''}{total_pnl:.2f}$"
    )
    lines.append(f"{'─'*28}")
    tp_label = f"ثابت {TP_FIXED_PCT*100:.1f}%" if TP_FIXED_PCT is not None else f"فراكتال ×{TP_RATIO}"
    sl_label = f"ثابت {SL_FIXED_PCT*100:.1f}%" if SL_FIXED_PCT is not None else "فراكتال"
    lines.append(f"🎯 TP: {tp_label}  |  🛑 SL: {sl_label}  |  رأس المال: ${CAPITAL_PER_SYMBOL:.0f}")
    return "\n".join(lines)

# ══════════════════════════════════════════════════════════════
#  FractalEngine
# ══════════════════════════════════════════════════════════════
class FractalEngine:
    def __init__(self, period=2):
        self.period = period
        self.buffer = []

    def add(self, candle):
        self.buffer.append(candle)
        needed = self.period * 2 + 1
        if len(self.buffer) < needed:
            return None, None, None
        window  = self.buffer[-needed:]
        mid     = self.period
        lows    = [c['low']  for c in window]
        highs   = [c['high'] for c in window]
        bullish = window[mid]['low']  == min(lows)
        bearish = window[mid]['high'] == max(highs)
        return bullish, bearish, window[mid]

# ══════════════════════════════════════════════════════════════
#  LevelStore
# ══════════════════════════════════════════════════════════════
class LevelStore:
    def __init__(self):
        self.resistances = []
        self.supports    = []

    def add_resistance(self, price, idx):
        self.resistances.append({'price': price, 'idx': idx})

    def add_support(self, price, idx):
        self.supports.append({'price': price, 'idx': idx})

    def last_resistance(self):
        return self.resistances[-1] if self.resistances else None

    def last_support(self):
        return self.supports[-1] if self.supports else None

    def remove_broken_resistances(self, close_price):
        self.resistances = [r for r in self.resistances if r['price'] > close_price]

# ══════════════════════════════════════════════════════════════
#  FakeoutFilterEngine
# ══════════════════════════════════════════════════════════════
class FakeoutFilterEngine:
    def __init__(self):
        self.volumes    = deque(maxlen=VOLUME_LOOKBACK)
        self.closes     = deque(maxlen=RSI_PERIOD + 1)
        self.highs      = deque(maxlen=ATR_PERIOD + 1)
        self.lows       = deque(maxlen=ATR_PERIOD + 1)

        self.rejected_volume = 0
        self.rejected_close  = 0
        self.rejected_atr    = 0
        self.rejected_rsi    = 0
        self.rejected_wick   = 0
        self.total_signals   = 0

    def update(self, c):
        vol = c.get('volume', 0)
        if vol > 0:
            self.volumes.append(vol)
        self.closes.append(c['close'])
        self.highs.append(c['high'])
        self.lows.append(c['low'])

    def _atr(self):
        if len(self.highs) < 2:
            return None
        trs = []
        H, L, C = list(self.highs), list(self.lows), list(self.closes)
        n = min(len(H), len(L), len(C))
        for i in range(1, n):
            tr = max(H[i]-L[i], abs(H[i]-C[i-1]), abs(L[i]-C[i-1]))
            trs.append(tr)
        return sum(trs)/len(trs) if trs else None

    def _rsi(self):
        closes = list(self.closes)
        if len(closes) < RSI_PERIOD + 1:
            return None
        gains = losses = 0.0
        for i in range(1, RSI_PERIOD + 1):
            d = closes[i] - closes[i-1]
            if d > 0: gains  += d
            else:     losses -= d
        ag = gains  / RSI_PERIOD
        al = losses / RSI_PERIOD
        if al == 0: return 100.0
        return 100 - (100 / (1 + ag/al))

    def is_valid_breakout(self, candle, resistance_price, sl_price):
        self.total_signals += 1

        if candle['close'] <= resistance_price:
            self.rejected_close += 1
            return False, "ظل فقط – الإغلاق داخل النطاق"

        cr = candle['high'] - candle['low']
        if cr > 0:
            wick = candle['high'] - max(candle['open'], candle['close'])
            if wick / cr > MAX_WICK_RATIO:
                self.rejected_wick += 1
                return False, f"ذيل رفض طويل (>{MAX_WICK_RATIO*100:.0f}% من النطاق)"

        if len(self.volumes) >= 5:
            avg = sum(self.volumes) / len(self.volumes)
            if avg > 0 and candle.get('volume', 0) < avg * VOLUME_MULTIPLIER:
                self.rejected_volume += 1
                return False, f"حجم ضعيف (<{VOLUME_MULTIPLIER}× المتوسط)"

        atr = self._atr()
        if atr and atr > 0:
            risk = candle['close'] - sl_price
            if risk > atr * MAX_ATR_MULTIPLIER:
                self.rejected_atr += 1
                return False, f"مخاطرة كبيرة (>{MAX_ATR_MULTIPLIER}× ATR)"

        rsi = self._rsi()
        if rsi and rsi >= RSI_OVERBOUGHT:
            self.rejected_rsi += 1
            return False, f"RSI تشبع شراء ({rsi:.1f} > {RSI_OVERBOUGHT})"

        return True, ""

# ══════════════════════════════════════════════════════════════
#  SymbolEngine – محرك صفقة لكل عملة
# ══════════════════════════════════════════════════════════════
class SymbolEngine:
    def __init__(self, symbol, telegram: TelegramBot):
        self.symbol   = symbol
        self.tg       = telegram
        self.capital  = CAPITAL_PER_SYMBOL
        self.equity   = CAPITAL_PER_SYMBOL
        self.peak     = CAPITAL_PER_SYMBOL
        self.max_dd   = 0.0
        self.wins = self.losses = 0
        self.total_commission   = 0.0
        self.candle_idx         = 0

        self.in_trade    = False
        self.entry_price = None
        self.sl = self.tp = None

        self.fractal = FractalEngine(PERIOD)
        self.levels  = LevelStore()
        self.flt     = FakeoutFilterEngine()

    def _dd(self):
        if self.equity > self.peak:
            self.peak = self.equity
        dd = (self.peak - self.equity) / self.peak * 100
        if dd > self.max_dd:
            self.max_dd = dd

    async def process(self, candle: dict):
        self.candle_idx += 1
        c = candle

        self.flt.update(c)

        bullish, bearish, mid = self.fractal.add(c)

        if bearish and mid:
            self.levels.add_resistance(mid['high'], self.candle_idx - PERIOD)
        if bullish and mid:
            self.levels.add_support(mid['low'], self.candle_idx - PERIOD)

        # ── فحص إغلاق الصفقة ──────────────────────────────
        if self.in_trade:
            hit_sl = c['low']  <= self.sl
            hit_tp = c['high'] >= self.tp
            if hit_sl or hit_tp:
                result     = 'TP' if hit_tp and not hit_sl else 'SL'
                exit_price = self.tp if result == 'TP' else self.sl
                await self._close(result, exit_price)
                return

        # ── فحص فتح صفقة ──────────────────────────────────
        if not self.in_trade:
            resistance = self.levels.last_resistance()
            support    = self.levels.last_support()
            if resistance and support:
                if c['close'] > resistance['price']:
                    sl_price = support['price']
                    risk     = c['close'] - sl_price
                    if risk <= 0 or (risk / c['close']) > 0.05:
                        self.levels.remove_broken_resistances(c['close'])
                        return

                    valid, reason = self.flt.is_valid_breakout(c, resistance['price'], sl_price)
                    if not valid:
                        self.levels.remove_broken_resistances(c['close'])
                        return

                    # ── حساب SL ──────────────────────────────────
                    # SL_FIXED_PCT = رقم → ثابت | None → فراكتال (القيمة الافتراضية)
                    if SL_FIXED_PCT is not None:
                        sl_price = c['close'] * (1 - SL_FIXED_PCT)
                    # إذا None تبقى sl_price = support['price'] كما هي

                    # ── حساب TP ──────────────────────────────────
                    # TP_FIXED_PCT = رقم → ثابت | None → فراكتال × TP_RATIO (الافتراضي)
                    risk = c['close'] - sl_price
                    if TP_FIXED_PCT is not None:
                        tp_price = c['close'] * (1 + TP_FIXED_PCT)
                    else:
                        tp_price = c['close'] + risk * TP_RATIO

                    self.entry_price = c['close']
                    self.sl          = sl_price
                    self.tp          = tp_price
                    self.in_trade    = True

                    comm = self.equity * COMMISSION
                    self.equity          -= comm
                    self.total_commission += comm

                    risk_usd = self.equity * (risk / c['close'])
                    await self.tg.send(
                        msg_open_trade(self.symbol, c['close'], sl_price, tp_price, self.equity, risk_usd)
                    )
                    log.info(f"[{self.symbol}] OPEN  @ {c['close']:.4f}  SL:{sl_price:.4f}  TP:{tp_price:.4f}")
                    self.levels.remove_broken_resistances(c['close'])

    async def _close(self, result, exit_price):
        pnl_pct = (exit_price - self.entry_price) / self.entry_price * 100
        pnl_usd = self.equity * (pnl_pct / 100)
        comm    = self.equity * COMMISSION
        self.equity           += pnl_usd - comm
        self.total_commission += comm

        if result == 'TP':
            self.wins += 1
            await self.tg.send(
                msg_close_win(self.symbol, self.entry_price, exit_price,
                              pnl_usd, pnl_pct, self.equity,
                              self.wins, self.losses)
            )
        else:
            self.losses += 1
            await self.tg.send(
                msg_close_loss(self.symbol, self.entry_price, exit_price,
                               pnl_usd, pnl_pct, self.equity,
                               self.wins, self.losses)
            )

        log.info(f"[{self.symbol}] {result}  pnl={pnl_pct:+.2f}%  equity=${self.equity:.2f}")
        self._dd()
        self.in_trade    = False
        self.entry_price = None

    def stats(self):
        return {
            'symbol':  self.symbol,
            'equity':  self.equity,
            'wins':    self.wins,
            'losses':  self.losses,
            'max_dd':  self.max_dd,
        }

# ══════════════════════════════════════════════════════════════
#  Binance REST – تحميل الشموع التاريخية
# ══════════════════════════════════════════════════════════════
async def fetch_historical(session, symbol, interval, limit=200):
    url = "https://api.binance.com/api/v3/klines"
    params = {"symbol": symbol, "interval": interval, "limit": limit}
    async with session.get(url, params=params) as r:
        data = await r.json()
    candles = []
    for k in data[:-1]:  # استبعاد الشمعة الحالية غير المكتملة
        candles.append({
            'open':   float(k[1]),
            'high':   float(k[2]),
            'low':    float(k[3]),
            'close':  float(k[4]),
            'volume': float(k[5]),
            'time':   int(k[0]),
        })
    return candles

# ══════════════════════════════════════════════════════════════
#  Binance WebSocket – استقبال الشموع اللايف
# ══════════════════════════════════════════════════════════════
BINANCE_WS = "wss://stream.binance.com:9443/stream"

def build_ws_url(symbols, interval):
    streams = "/".join(f"{s.lower()}@kline_{interval}" for s in symbols)
    return f"{BINANCE_WS}?streams={streams}"

def parse_kline(msg):
    k = msg['data']['k']
    return {
        'symbol':  msg['data']['s'],
        'open':    float(k['o']),
        'high':    float(k['h']),
        'low':     float(k['l']),
        'close':   float(k['c']),
        'volume':  float(k['v']),
        'time':    int(k['t']),
        'closed':  k['x'],    # True = الشمعة مكتملة
    }

# ══════════════════════════════════════════════════════════════
#  Daily Stats Task
# ══════════════════════════════════════════════════════════════
async def daily_report_task(engines: dict, tg: TelegramBot):
    """يرسل تقريراً يومياً كل 24 ساعة."""
    await asyncio.sleep(3600)  # أول تقرير بعد ساعة
    while True:
        records = [e.stats() for e in engines.values()]
        await tg.send(msg_daily_stats(records))
        await asyncio.sleep(24 * 3600)

# ══════════════════════════════════════════════════════════════
#  Main
# ══════════════════════════════════════════════════════════════
async def main():
    loop = asyncio.get_event_loop()

    tg = TelegramBot(TELEGRAM_TOKEN, TELEGRAM_CHAT_ID)
    tg.start(loop)

    # استخراج الـ IP
    current_bot_ip = "غير متاح"
    try:
        import requests
        current_bot_ip = requests.get('https://api.ipify.org', timeout=10).text
        print("\n" + "="*40)
        print(f"🤖 عنوان الـ IP الحالي للبوت هو: {current_bot_ip}")
        print("="*40 + "\n")
    except Exception as e:
        print(f"❌ فشل استخراج الـ IP بسبب: {e}")

    await tg.send(
        f"🤖 <b>بوت الفراكتال يعمل الآن</b>\n"
        f"🤖 عنوان الـ IP الحالي للبوت هو: {current_bot_ip}\n"
        f"{'─'*28}\n"
        f"📈 العملات: {', '.join(SYMBOLS)}\n"
        f"⏱ الإطار الزمني: {TIMEFRAME}\n"
        f"💰 رأس المال لكل عملة: ${CAPITAL_PER_SYMBOL:,.0f}\n"
        f"🎯 TP: {'ثابت '+str(TP_FIXED_PCT*100)+'%' if TP_FIXED_PCT is not None else 'فراكتال ×'+str(TP_RATIO)}\n"
        f"🛑 SL: {'ثابت '+str(SL_FIXED_PCT*100)+'%' if SL_FIXED_PCT is not None else 'فراكتال'}\n"
        f"🛡 فلاتر الاختراق الكاذب: مفعّلة\n"
        f"{'─'*28}\n"
        f"🕐 {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}"
    )

    # تهيئة المحركات
    engines: dict[str, SymbolEngine] = {s: SymbolEngine(s, tg) for s in SYMBOLS}

    # تحميل البيانات التاريخية
    log.info("📥 تحميل الشموع التاريخية من بينانس...")
    async with aiohttp.ClientSession() as session:
        for sym in SYMBOLS:
            try:
                candles = await fetch_historical(session, sym, TIMEFRAME, HISTORICAL_CANDLES)
                engine  = engines[sym]
                for c in candles:
                    await engine.process(c)
                log.info(f"  ✅ {sym}: تم تحميل {len(candles)} شمعة")
                await asyncio.sleep(0.3)
            except Exception as e:
                log.error(f"  ❌ {sym}: خطأ في تحميل البيانات – {e}")

    # ── تقرير فوري بعد تحميل البيانات التاريخية ──────────
    records = [e.stats() for e in engines.values()]
    await tg.send(msg_historical_report(records))
    log.info("📋 تم إرسال تقرير البيانات التاريخية")
    # ──────────────────────────────────────────────────────

    await tg.send(f"✅ <b>تم تحميل البيانات التاريخية</b>\nجاهز لاستقبال الشموع اللايف...")

    # بدء مهمة التقرير اليومي
    loop.create_task(daily_report_task(engines, tg))

    # WebSocket اللايف
    ws_url = build_ws_url(SYMBOLS, TIMEFRAME)
    log.info(f"🔌 الاتصال بـ WebSocket بينانس...")

    while True:
        try:
            async with aiohttp.ClientSession() as session:
                async with session.ws_connect(ws_url, heartbeat=30) as ws:
                    log.info("✅ متصل بـ WebSocket بينانس")
                    async for msg in ws:
                        if msg.type == aiohttp.WSMsgType.TEXT:
                            data = json.loads(msg.data)
                            k    = parse_kline(data)
                            if k['closed']:
                                sym = k['symbol']
                                if sym in engines:
                                    await engines[sym].process(k)
                        elif msg.type in (aiohttp.WSMsgType.ERROR, aiohttp.WSMsgType.CLOSE):
                            log.warning("WebSocket أُغلق – إعادة الاتصال...")
                            break
        except Exception as e:
            log.error(f"خطأ في WebSocket: {e} – إعادة الاتصال بعد 5 ثوانٍ")
            await asyncio.sleep(5)


# ==========================================
# 4. نقطة الانطلاق
# ==========================================
if __name__ == "__main__":
    keep_alive()
    asyncio.run(main())
