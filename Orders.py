from binance.client import Client
from decimal import Decimal, ROUND_DOWN
import time
import os
#================================
                        #Set Api
#================================

api_key    = os.environ.get("BINANCE_API_KEY")
api_secret = os.environ.get("BINANCE_API_SECRET")
client = Client(api_key, api_secret)
global price_global
price_global=0
#================================
                        #buy Order
#================================
def buy_market(symbol,USDT):
    #quoteOrderQty=Qty
    buy_order = client.order_market_buy(symbol=symbol,    quoteOrderQty=USDT)
    print("buy_Marcket_Done")
    return buy_order     
#================================
                        #Cancel Order
#================================

def cancel_all_open_orders( symbol=None):

    orders = client.get_open_orders(symbol=symbol) if symbol else client.get_open_orders()

    if not orders:
        print("No open orders")
        return

    for order in orders:
        try:
            client.cancel_order(
                symbol=order['symbol'],
                orderId=order['orderId']
            )
            print(f"Cancelled: {order['symbol']} | {order['orderId']}")
        except Exception:
            # تجاهل أي أمر غير موجود أو منفذ
            continue

    print("Open orders Cancel done")
#================================
                        #Get Current
#================================

def get_largest_asset():
    #client = Client(api_key, api_secret)

    account = client.get_account()
    balances = account['balances']

    max_asset = None
    max_value = 0

    for b in balances:
        asset = b['asset']
        free = float(b['free'])
        locked = float(b['locked'])
        total = free + locked

        if total == 0:
            continue

        try:
            if asset == "USDT":
                value = total
            else:
                symbol = asset + "USDT"
                ticker = client.get_symbol_ticker(symbol=symbol)
                price = float(ticker['price'])
                value = total * price

            if value > max_value:
                x=max_value = value
                y=max_asset = asset

        except:
            # إذا الزوج غير موجود (مثل عملات غير مدعومة مقابل USDT)
            continue
    return x,y
#================================
                        #Sell All
#================================

def sell_All():
    cancel_all_open_orders()
    # ====== جلب كل الأرصدة ======
    account = client.get_account()
    balances = account['balances']

    # ====== جلب رصيد USDT ======
    usdt_balance = 0.0
    
    for b in balances:
        if b['asset'] == "USDT":
            usdt_balance = float(b['free'])
            break

    print("USDT Balance:", usdt_balance)

    # ====== المرور على كل العملات ======
    for b in balances:
        asset = b['asset']
        free_qty = float(b['free'])

        if free_qty <= 0 or asset == "USDT":
            continue

        symbol = asset + "USDT"

        try:
            # ====== جلب السعر ======
            ticker = client.get_symbol_ticker(symbol=symbol)
            price = float(ticker['price'])

            value = free_qty * price

            #print(f"{asset} value:", value)

            # ====== الشرط ======
            if value > usdt_balance:

                # ====== إلغاء أوامر الزوج ====
                
                # ====== جلب step size ======
                info = client.get_symbol_info(symbol)
                step_size = float([f for f in info['filters'] if f['filterType'] == 'LOT_SIZE'][0]['stepSize'])

                def format_qty(qty, step):
                    qty = Decimal(str(qty))
                    step = Decimal(str(step))
                    return float(qty.quantize(step, rounding=ROUND_DOWN))

                quantity = format_qty(free_qty, step_size)
                quantity_str = format(quantity, 'f')

                print(f"Selling {asset} ...")

                # ====== بيع ======
                client.order_market_sell(
                    symbol=symbol,
                    quantity=quantity_str
                )

                #print(f"{asset} SOLD")

        except Exception as e:
            # تجاهل العملات التي ليس لها زوج USDT
            print(f"Skip {asset}: {e}")
            #print("Sell All Done")

#================================
                        #OCO Buy
#================================
def oco(symbol, TP, SL):

    global price_global

    # ====== شراء ======
    usdt_balance = client.get_asset_balance(asset='USDT')

    if not usdt_balance:
        raise Exception("No USDT Balance")

    # نستخدم 95% فقط
    usdt = round(float(usdt_balance['free']) * 0.95, 2)

    if usdt <= 0:
        raise Exception("USDT balance too low")

    buy_order = client.order_market_buy(
        symbol=symbol,
        quoteOrderQty=usdt
    )

    print("buy_Market_Done")

    # ====== استخراج سعر الشراء ======
    for fill in buy_order['fills']:
        price_global = float(fill['price'])

    # ====== معلومات السوق ======
    info = client.get_symbol_info(symbol)

    tick_size = Decimal(str(
        [f for f in info['filters']
         if f['filterType'] == 'PRICE_FILTER'][0]['tickSize']
    ))

    step_size = Decimal(str(
        [f for f in info['filters']
         if f['filterType'] == 'LOT_SIZE'][0]['stepSize']
    ))

    # ====== دوال precision ======
    def fix_price(p):
        p = Decimal(str(p))
        return (p // tick_size) * tick_size

    def fix_qty(q):
        q = Decimal(str(q))
        return (q // step_size) * step_size

    # ====== TP / SL ======
    TP = fix_price(TP)
    SL = fix_price(SL)

    # ====== الرصيد بعد الشراء ======
    base_asset = symbol.replace("USDT", "")
    balance = client.get_asset_balance(asset=base_asset)

    if not balance:
        raise Exception("No asset balance found")

    qty = Decimal(balance['free']) + Decimal(balance['locked'])
    qty = fix_qty(qty)

    if qty <= 0:
        raise Exception("Invalid quantity")

    quantity_str = format(qty, 'f')

    time.sleep(1)

    # ====== OCO ======
    oco_order = client.create_oco_order(

        symbol=symbol,
        side='SELL',
        quantity=quantity_str,

        aboveType='LIMIT_MAKER',
        abovePrice=str(TP),

        belowType='STOP_LOSS_LIMIT',
        belowStopPrice=str(SL),
        belowPrice=str(
            fix_price(SL * Decimal('0.99'))
        ),

        belowTimeInForce='GTC'
    )

    print("OCO Buy Done")

    return price_global
#================================
                        #OCO Reset TP,Sl
#================================
def oco_reset_Tp_Sl( symbol, TP, SL):

    cancel_all_open_orders(symbol)

    # ====== معلومات السوق ======
    info = client.get_symbol_info(symbol)

    tick_size = Decimal(str([f for f in info['filters'] if f['filterType'] == 'PRICE_FILTER'][0]['tickSize']))
    step_size = Decimal(str([f for f in info['filters'] if f['filterType'] == 'LOT_SIZE'][0]['stepSize']))

    # ====== دوال دقيقة جداً ======
    def fix_price(p):
        p = Decimal(str(p))
        return (p // tick_size) * tick_size

    def fix_qty(q):
        q = Decimal(str(q))
        return (q // step_size) * step_size

    # ====== TP / SL ======
    TP = fix_price(TP)
    SL = fix_price(SL)

    # ====== الرصيد ======
    base_asset = symbol.replace("USDT", "")
    balance = client.get_asset_balance(asset=base_asset)

    if not balance:
        raise Exception("No balance found")

    qty = Decimal(balance['free']) + Decimal(balance['locked'])
    qty = fix_qty(qty)

    if qty <= 0:
        raise Exception("Invalid quantity")

    quantity_str = format(qty, 'f')

    time.sleep(1)

    # ====== OCO ======
    oco_order = client.create_oco_order(
        symbol=symbol,
        side='SELL',
        quantity=quantity_str,

        aboveType='LIMIT_MAKER',
        abovePrice=str(TP),

        belowType='STOP_LOSS_LIMIT',
        belowStopPrice=str(SL),
        belowPrice=str(fix_price(SL * Decimal('0.99'))),

        belowTimeInForce='GTC'
    )

    print("OCO Done")
    return oco_order
    
    # ====== جلب step size ======
    info = client.get_symbol_info(symbol)
    step_size = float([f for f in info['filters'] if f['filterType'] == 'LOT_SIZE'][0]['stepSize'])

    # ====== ضبط الكمية ======
    def format_qty(qty, step):
        qty = Decimal(str(qty))
        step = Decimal(str(step))
        return float(qty.quantize(step, rounding=ROUND_DOWN))

    quantity = format_qty(free_qty, step_size)
    quantity_str = format(quantity, 'f')

    time.sleep(1)

    # ====== إنشاء OCO ======
    oco_order = client.create_oco_order(
        symbol=symbol,
        side='SELL',
        quantity=quantity_str,

        # Take Profit
        aboveType='LIMIT_MAKER',
        abovePrice=str(TP),

        # Stop Loss
        belowType='STOP_LOSS_LIMIT',
        belowStopPrice=str(SL),
        belowPrice=str(float(SL) * 0.99),
        belowTimeInForce='GTC'
    )

    print("OCO Reset TP SL Done")
    return oco_order

#================================
                        #TESTER
#================================



        
#sell_All()
#
#oco("SSVUSDT",2.999,2.703)
#time.sleep(20)

#oco_reset_Tp_Sl("SSVUSDT",2.991,2.703)
#time.sleep(20)
#sell_All()
#print(price_global)
#check_orders()


    
#oco_reset_Tp_Sl("SSVUSDT",2.961,2.703)
#سعر العملة الان2.834
#time.sleep(20)
