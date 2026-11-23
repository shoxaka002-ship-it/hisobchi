import os, asyncio, logging
from datetime import datetime, timedelta, timezone
import aiosqlite
from aiogram import Bot, Dispatcher, F
from aiogram.filters import CommandStart, Command
from aiogram.types import Message, CallbackQuery, InlineKeyboardMarkup, InlineKeyboardButton
from aiogram.fsm.state import State, StatesGroup
from aiogram.fsm.context import FSMContext
from aiogram.fsm.storage.memory import MemoryStorage

TOKEN=os.getenv("BOT_TOKEN","")
ADMIN_ID=int(os.getenv("ADMIN_ID","6945521821"))
DB=os.getenv("DB_PATH","hisobchi.db")
TON=os.getenv("TON_WALLET","UQBECbtI0XnGLO5lV9gfOQEkpfJQhAxF9_k58FtE6A2B4o2b")
dp=Dispatcher(storage=MemoryStorage())
logging.basicConfig(level=logging.INFO)

class Pay(StatesGroup):
    amount=State(); name=State(); phone=State(); method=State(); proof=State()
class Adm(StatesGroup):
    card=State(); ton=State(); search=State(); broadcast=State()

def markup(rows): return InlineKeyboardMarkup(inline_keyboard=rows)
def usermenu(): return markup([[InlineKeyboardButton(text="💳 Pul kiritish",callback_data="deposit")],[InlineKeyboardButton(text="📊 To‘lovlarim",callback_data="mine")],[InlineKeyboardButton(text="ℹ️ Yordam",callback_data="help")]])
def adminmenu(): return markup([[InlineKeyboardButton(text="📥 Kutilayotgan to‘lovlar",callback_data="pending")],[InlineKeyboardButton(text="📊 Hisobot",callback_data="report")],[InlineKeyboardButton(text="🔎 Ism-familiya qidirish",callback_data="search")],[InlineKeyboardButton(text="💳 Karta qo‘shish",callback_data="card"),InlineKeyboardButton(text="💎 TON hamyon",callback_data="ton")],[InlineKeyboardButton(text="📣 Hammaga xabar",callback_data="broadcast")]])
async def db():
    c=await aiosqlite.connect(DB); c.row_factory=aiosqlite.Row; return c
def isadmin(uid): return uid==ADMIN_ID
async def init():
    async with await db() as c:
        await c.executescript("""CREATE TABLE IF NOT EXISTS users(uid INTEGER PRIMARY KEY,username TEXT,name TEXT,phone TEXT,created TEXT);
        CREATE TABLE IF NOT EXISTS methods(id INTEGER PRIMARY KEY AUTOINCREMENT,kind TEXT,title TEXT,details TEXT,active INTEGER DEFAULT 1);
        CREATE TABLE IF NOT EXISTS payments(id INTEGER PRIMARY KEY AUTOINCREMENT,uid INTEGER,amount REAL,name TEXT,phone TEXT,method TEXT,photo TEXT,proof TEXT,status TEXT DEFAULT 'pending',created TEXT,reviewed TEXT);""")
        cur=await c.execute("SELECT COUNT(*) n FROM methods")
        if (await cur.fetchone())["n"]==0: await c.execute("INSERT INTO methods(kind,title,details) VALUES('TON','TON (Tonkeeper)',?)",(TON,))
        await c.commit()

@dp.message(CommandStart())
async def start(m:Message,state:FSMContext):
    await state.clear()
    async with await db() as c:
        await c.execute("INSERT INTO users(uid,username,created) VALUES(?,?,?) ON CONFLICT(uid) DO UPDATE SET username=excluded.username",(m.from_user.id,m.from_user.username,datetime.now(timezone.utc).isoformat())); await c.commit()
    await m.answer("Assalomu alaykum! HISOBCHI BOTga xush kelibsiz.",reply_markup=usermenu())

@dp.message(Command("admin"))
async def admin_cmd(m:Message):
    if isadmin(m.from_user.id): await m.answer("Admin paneli:",reply_markup=adminmenu())

@dp.callback_query(F.data=="help")
async def help_cb(q:CallbackQuery):
    await q.message.answer("Pul kiritish bo‘limida summa, ism-familiya va telefon raqamingizni kiriting. Chek admin tekshiruviga yuboriladi."); await q.answer()

@dp.callback_query(F.data=="deposit")
async def deposit(q:CallbackQuery,state:FSMContext):
    await state.set_state(Pay.amount); await q.message.answer("Summani so‘mda kiriting (masalan 150000):"); await q.answer()

@dp.message(Pay.amount)
async def amount(m:Message,state:FSMContext):
    try:
        v=float(m.text.replace(" ","").replace(",","."))
        if v<=0: raise ValueError()
    except: return await m.answer("Summani raqam bilan kiriting.")
    await state.update_data(amount=v); await state.set_state(Pay.name); await m.answer("Ism-familiyangizni yozing:")

@dp.message(Pay.name)
async def name(m:Message,state:FSMContext):
    if not m.text or len(m.text.strip())<3: return await m.answer("Ism-familiyani to‘liq yozing.")
    await state.update_data(name=m.text.strip()); await state.set_state(Pay.phone); await m.answer("Telefon raqamingizni yozing:")

@dp.message(Pay.phone)
async def phone(m:Message,state:FSMContext):
    if not m.text or len(m.text.strip())<7: return await m.answer("Telefon raqamini to‘g‘ri yozing.")
    await state.update_data(phone=m.text.strip())
    async with await db() as c:
        cur=await c.execute("SELECT id,title FROM methods WHERE active=1 ORDER BY id"); rows=await cur.fetchall()
    buttons=[[InlineKeyboardButton(text=r["title"],callback_data=f"method:{r['id']}")] for r in rows]
    if not buttons: await state.clear(); return await m.answer("To‘lov usullari sozlanmagan.")
    await state.set_state(Pay.method); await m.answer("To‘lov usulini tanlang:",reply_markup=markup(buttons))

@dp.callback_query(Pay.method,F.data.startswith("method:"))
async def choose_method(q:CallbackQuery,state:FSMContext):
    mid=int(q.data.split(":")[1])
    async with await db() as c:
        cur=await c.execute("SELECT * FROM methods WHERE id=? AND active=1",(mid,)); r=await cur.fetchone()
    if not r: return await q.answer("Usul topilmadi",show_alert=True)
    await state.update_data(method=r["title"],details=r["details"],kind=r["kind"]); d=await state.get_data()
    if r["kind"]=="TON": msg=f"💎 TON hamyon:\n`{r['details']}`\n\nTON miqdorini o‘zingiz kiriting. Yuborgach tranzaksiya havolasi/hashini yoki chek rasmini jo‘nating."
    else: msg=f"💳 {r['title']}\n{r['details']}\n\n{d['amount']:,.0f} so‘m yuboring va chek rasmini jo‘nating."
    await state.set_state(Pay.proof); await q.message.answer(msg,parse_mode="Markdown"); await q.answer()

@dp.message(Pay.proof)
async def proof(m:Message,state:FSMContext,bot:Bot):
    d=await state.get_data(); photo=m.photo[-1].file_id if m.photo else None; txt=m.text.strip() if m.text else None
    if not photo and not txt: return await m.answer("Chek rasmini yoki TON tranzaksiya havolasini yuboring.")
    async with await db() as c:
        cur=await c.execute("INSERT INTO payments(uid,amount,name,phone,method,photo,proof,created) VALUES(?,?,?,?,?,?,?,?)",(m.from_user.id,d["amount"],d["name"],d["phone"],d["method"],photo,txt,datetime.now(timezone.utc).isoformat())); pid=cur.lastrowid
        await c.execute("UPDATE users SET name=?,phone=? WHERE uid=?",(d["name"],d["phone"],m.from_user.id)); await c.commit()
    buttons=markup([[InlineKeyboardButton(text="✅ Tasdiqlash",callback_data=f"ok:{pid}"),InlineKeyboardButton(text="❌ Rad etish",callback_data=f"no:{pid}")]])
    cap=f"Yangi to‘lov #{pid}\n{d['name']}\n{d['phone']}\n{d['amount']:,.0f} so‘m\n{d['method']}\nTelegram ID: {m.from_user.id}"
    if photo: await bot.send_photo(ADMIN_ID,photo,caption=cap,reply_markup=buttons)
    else: await bot.send_message(ADMIN_ID,cap+"\n"+txt,reply_markup=buttons)
    await state.clear(); await m.answer("✅ Ma’lumot qabul qilindi. Admin tekshiradi.",reply_markup=usermenu())

@dp.callback_query(F.data.startswith(("ok:","no:")))
async def review(q:CallbackQuery,bot:Bot):
    if not isadmin(q.from_user.id): return await q.answer("Ruxsat yo‘q",show_alert=True)
    act,pid=q.data.split(":"); status="approved" if act=="ok" else "rejected"
    async with await db() as c:
        cur=await c.execute("SELECT * FROM payments WHERE id=?",(int(pid),)); p=await cur.fetchone()
        if not p or p["status"]!="pending": return await q.answer("Allaqachon ko‘rib chiqilgan",show_alert=True)
        await c.execute("UPDATE payments SET status=?,reviewed=? WHERE id=?",(status,datetime.now(timezone.utc).isoformat(),int(pid))); await c.commit()
    await bot.send_message(p["uid"],("✅ To‘lov tasdiqlandi." if status=="approved" else "❌ To‘lov rad etildi.")+f"\n#{pid} — {p['amount']:,.0f} so‘m")
    await q.message.edit_reply_markup(reply_markup=None); await q.answer("Saqlandi")

@dp.callback_query(F.data=="mine")
async def mine(q:CallbackQuery):
    async with await db() as c:
        cur=await c.execute("SELECT * FROM payments WHERE uid=? ORDER BY id DESC LIMIT 10",(q.from_user.id,)); rows=await cur.fetchall()
    await q.message.answer("\n".join([f"#{r['id']} {r['amount']:,.0f} so‘m — {r['method']} — {r['status']}" for r in rows]) if rows else "Hali to‘lovlaringiz yo‘q."); await q.answer()

@dp.callback_query(F.data=="report")
async def report(q:CallbackQuery):
    if not isadmin(q.from_user.id): return await q.answer("Ruxsat yo‘q",show_alert=True)
    now=datetime.now(timezone.utc)
    async with await db() as c:
        async def total(s):
            cur=await c.execute("SELECT COALESCE(SUM(amount),0) v,COUNT(*) n FROM payments WHERE status='approved' AND created>=?",(s,)); return await cur.fetchone()
        d=await total(now.replace(hour=0,minute=0,second=0,microsecond=0).isoformat()); w=await total((now-timedelta(days=7)).isoformat()); mo=await total((now-timedelta(days=30)).isoformat())
        cur=await c.execute("SELECT COUNT(*) n FROM payments WHERE status='pending'"); pend=(await cur.fetchone())["n"]
        cur=await c.execute("SELECT COUNT(*) n FROM users"); users=(await cur.fetchone())["n"]
    await q.message.answer(f"📊 HISOBOT\nBugun: {d['v']:,.0f} so‘m ({d['n']} ta)\n7 kun: {w['v']:,.0f} so‘m ({w['n']} ta)\n30 kun: {mo['v']:,.0f} so‘m ({mo['n']} ta)\nKutilmoqda: {pend}\nFoydalanuvchilar: {users}"); await q.answer()

@dp.callback_query(F.data=="pending")
async def pending(q:CallbackQuery):
    if not isadmin(q.from_user.id): return await q.answer("Ruxsat yo‘q",show_alert=True)
    async with await db() as c:
        cur=await c.execute("SELECT * FROM payments WHERE status='pending' ORDER BY id DESC LIMIT 20"); rows=await cur.fetchall()
    if not rows: await q.message.answer("Kutilayotgan to‘lov yo‘q.")
    for p in rows:
        kb=markup([[InlineKeyboardButton(text="✅ Tasdiqlash",callback_data=f"ok:{p['id']}"),InlineKeyboardButton(text="❌ Rad etish",callback_data=f"no:{p['id']}")]])
        t=f"#{p['id']} {p['name']} | {p['phone']}\n{p['amount']:,.0f} so‘m | {p['method']}\nID {p['uid']}"
        if p["photo"]: await q.message.answer_photo(p["photo"],caption=t,reply_markup=kb)
        else: await q.message.answer(t+"\n"+(p["proof"] or ""),reply_markup=kb)
    await q.answer()

@dp.callback_query(F.data=="card")
async def card_start(q:CallbackQuery,state:FSMContext):
    if not isadmin(q.from_user.id): return await q.answer("Ruxsat yo‘q",show_alert=True)
    await state.set_state(Adm.card); await q.message.answer("Karta ma’lumotini yuboring:\nVISA|karta raqami|egasi|bank\nYoki UZCARD|karta raqami|egasi|bank"); await q.answer()
@dp.message(Adm.card)
async def card_save(m:Message,state:FSMContext):
    if not isadmin(m.from_user.id): return
    a=[x.strip() for x in (m.text or "").split("|")]
    if len(a)!=4 or a[0].upper() not in ("VISA","UZCARD"): return await m.answer("Format xato. VISA|raqam|egasi|bank")
    async with await db() as c: await c.execute("INSERT INTO methods(kind,title,details) VALUES('CARD',?,?)",(a[0].upper(),f"Karta: {a[1]}\nEgasi: {a[2]}\nBank: {a[3]}")); await c.commit()
    await state.clear(); await m.answer("Karta qo‘shildi.",reply_markup=adminmenu())

@dp.callback_query(F.data=="ton")
async def ton_start(q:CallbackQuery,state:FSMContext):
    if not isadmin(q.from_user.id): return await q.answer("Ruxsat yo‘q",show_alert=True)
    await state.set_state(Adm.ton); await q.message.answer("Yangi TON hamyon manzilini yuboring:"); await q.answer()
@dp.message(Adm.ton)
async def ton_save(m:Message,state:FSMContext):
    if not isadmin(m.from_user.id): return
    a=(m.text or "").strip()
    if len(a)<30: return await m.answer("Manzil noto‘g‘ri ko‘rinadi.")
    async with await db() as c:
        await c.execute("UPDATE methods SET active=0 WHERE kind='TON'")
        await c.execute("INSERT INTO methods(kind,title,details) VALUES('TON','TON (Tonkeeper)',?)",(a,)); await c.commit()
    await state.clear(); await m.answer("TON hamyon yangilandi.",reply_markup=adminmenu())

@dp.callback_query(F.data=="search")
async def search_start(q:CallbackQuery,state:FSMContext):
    if not isadmin(q.from_user.id): return await q.answer("Ruxsat yo‘q",show_alert=True)
    await state.set_state(Adm.search); await q.message.answer("Ism yoki familiyani yozing:"); await q.answer()
@dp.message(Adm.search)
async def search_do(m:Message,state:FSMContext):
    if not isadmin(m.from_user.id): return
    async with await db() as c:
        cur=await c.execute("SELECT * FROM payments WHERE name LIKE ? ORDER BY id DESC LIMIT 20",(f"%{(m.text or '').strip()}%",)); rows=await cur.fetchall()
    await state.clear(); await m.answer("\n".join([f"#{r['id']} {r['name']} | {r['phone']} | {r['amount']:,.0f} | {r['status']}" for r in rows]) if rows else "Topilmadi.")

@dp.callback_query(F.data=="broadcast")
async def broadcast_start(q:CallbackQuery,state:FSMContext):
    if not isadmin(q.from_user.id): return await q.answer("Ruxsat yo‘q",show_alert=True)
    await state.set_state(Adm.broadcast); await q.message.answer("Hammaga yuboriladigan xabarni yozing:"); await q.answer()
@dp.message(Adm.broadcast)
async def broadcast_do(m:Message,state:FSMContext,bot:Bot):
    if not isadmin(m.from_user.id): return
    async with await db() as c:
        cur=await c.execute("SELECT uid FROM users"); ids=[r["uid"] for r in await cur.fetchall()]
    sent=0
    for uid in ids:
        try: await bot.send_message(uid,m.text or ""); sent+=1
        except Exception: pass
    await state.clear(); await m.answer(f"{sent} kishiga yuborildi.",reply_markup=adminmenu())

async def main():
    if not TOKEN: raise RuntimeError("BOT_TOKEN ni Render sozlamalariga kiriting.")
    await init(); await dp.start_polling(Bot(TOKEN))
if __name__=="__main__": asyncio.run(main())
