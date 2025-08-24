import discord
import random
import sqlite3
import asyncio
import os
from datetime import datetime, timedelta
from discord.ext import commands

# ---------------- CONFIG ----------------
TOKEN = os.getenv("DISCORD_TOKEN")  # ⚠️ Token via Render
PREFIX = "!"
INITIAL_BALANCE = 1000
DAILY_REWARD = 200
DAILY_COOLDOWN_HOURS = 20
DATABASE = "casino.db"

intents = discord.Intents.default()
intents.message_content = True
bot = commands.Bot(command_prefix=PREFIX, intents=intents)

db_lock = asyncio.Lock()

# ------------- BASE DE DONNÉES -------------
def init_db():
    con = sqlite3.connect(DATABASE)
    cur = con.cursor()
    cur.execute("""CREATE TABLE IF NOT EXISTS users (
        user_id INTEGER PRIMARY KEY,
        balance INTEGER NOT NULL,
        last_daily TEXT,
        points_temp INTEGER NOT NULL DEFAULT 0
    )""")
    con.commit()
    con.close()

def ensure_user(user_id):
    con = sqlite3.connect(DATABASE)
    cur = con.cursor()
    cur.execute("SELECT * FROM users WHERE user_id=?", (user_id,))
    if cur.fetchone() is None:
        cur.execute("INSERT INTO users (user_id, balance, last_daily, points_temp) VALUES (?, ?, ?, ?)",
                    (user_id, INITIAL_BALANCE, None, 0))
    con.commit()
    con.close()

def get_balance(user_id):
    con = sqlite3.connect(DATABASE)
    cur = con.cursor()
    cur.execute("SELECT balance FROM users WHERE user_id=?", (user_id,))
    bal = cur.fetchone()[0]
    con.close()
    return bal

def update_balance(user_id, amount):
    con = sqlite3.connect(DATABASE)
    cur = con.cursor()
    cur.execute("SELECT balance FROM users WHERE user_id=?", (user_id,))
    bal = cur.fetchone()[0]
    new_bal = bal + amount
    if new_bal < 0:
        con.close()
        return None
    cur.execute("UPDATE users SET balance=? WHERE user_id=?", (new_bal, user_id))
    con.commit()
    con.close()
    return new_bal

def get_last_daily(user_id):
    con = sqlite3.connect(DATABASE)
    cur = con.cursor()
    cur.execute("SELECT last_daily FROM users WHERE user_id=?", (user_id,))
    res = cur.fetchone()
    con.close()
    return datetime.fromisoformat(res[0]) if res and res[0] else None

def set_last_daily(user_id, when):
    con = sqlite3.connect(DATABASE)
    cur = con.cursor()
    cur.execute("UPDATE users SET last_daily=? WHERE user_id=?", (when.isoformat(), user_id))
    con.commit()
    con.close()

# ---------------- POINTS EXTERNES ----------------
def get_points(user_id):
    con = sqlite3.connect(DATABASE)
    cur = con.cursor()
    cur.execute("SELECT points_temp FROM users WHERE user_id=?", (user_id,))
    res = cur.fetchone()
    con.close()
    return res[0] if res else 0

def update_points(user_id, amount):
    con = sqlite3.connect(DATABASE)
    cur = con.cursor()
    cur.execute("SELECT points_temp FROM users WHERE user_id=?", (user_id,))
    current = cur.fetchone()[0]
    new_points = max(0, current + amount)
    cur.execute("UPDATE users SET points_temp=? WHERE user_id=?", (new_points, user_id))
    con.commit()
    con.close()
    return new_points

# ---------------- COMMANDES ----------------
@bot.event
async def on_ready():
    init_db()
    print(f"✅ Connecté en tant que {bot.user}")

@bot.command()
async def start(ctx):
    ensure_user(ctx.author.id)
    await ctx.send(f"{ctx.author.mention} ton compte casino est prêt avec {INITIAL_BALANCE} 🪙 !")

@bot.command()
async def balance(ctx):
    ensure_user(ctx.author.id)
    bal = get_balance(ctx.author.id)
    await ctx.send(f"{ctx.author.mention}, tu as {bal} 🪙")

@bot.command()
async def daily(ctx):
    ensure_user(ctx.author.id)
    last = get_last_daily(ctx.author.id)
    now = datetime.utcnow()
    if last and now - last < timedelta(hours=DAILY_COOLDOWN_HOURS):
        restant = timedelta(hours=DAILY_COOLDOWN_HOURS) - (now - last)
        h = restant.seconds // 3600
        m = (restant.seconds % 3600) // 60
        await ctx.send(f"⏳ Attends encore {h}h{m}m pour ton prochain daily.")
        return
    update_balance(ctx.author.id, DAILY_REWARD)
    set_last_daily(ctx.author.id, now)
    await ctx.send(f"🎁 {ctx.author.mention}, tu as reçu {DAILY_REWARD} 🪙 !")

@bot.command()
async def convert(ctx, points: int):
    ensure_user(ctx.author.id)
    current_points = get_points(ctx.author.id)
    if points <= 0 or points > current_points:
        await ctx.send("❌ Montant invalide.")
        return
    update_points(ctx.author.id, -points)
    update_balance(ctx.author.id, points)
    await ctx.send(f"✅ {ctx.author.mention} a converti {points} points en {points} 🪙 !")

# ---------------- MINI-JEUX ----------------
@bot.command()
async def slot(ctx, mise: int):
    ensure_user(ctx.author.id)
    bal = get_balance(ctx.author.id)
    if mise <= 0 or mise > bal:
        await ctx.send("❌ Mise invalide.")
        return
    symbols = ["🍒", "🍋", "🍇", "🍉", "⭐", "7️⃣"]
    result = [random.choice(symbols) for _ in range(3)]
    await ctx.send(" | ".join(result))
    if len(set(result)) == 1:
        gain = mise * 5
        update_balance(ctx.author.id, gain)
        await ctx.send(f"🎉 JACKPOT ! Tu gagnes {gain} 🪙")
    elif len(set(result)) == 2:
        gain = mise * 2
        update_balance(ctx.author.id, gain)
        await ctx.send(f"✨ Pas mal ! Tu gagnes {gain} 🪙")
    else:
        update_balance(ctx.author.id, -mise)
        await ctx.send(f"😢 Perdu {mise} 🪙")

@bot.command()
async def coinflip(ctx, mise: int, choix: str):
    ensure_user(ctx.author.id)
    bal = get_balance(ctx.author.id)
    if mise <= 0 or mise > bal:
        await ctx.send("❌ Mise invalide.")
        return
    choix = choix.lower()
    if choix not in ["pile", "face"]:
        await ctx.send("❌ Choix invalide (pile/face).")
        return
    result = random.choice(["pile", "face"])
    await ctx.send(f"🪙 La pièce tombe sur {result}")
    if choix == result:
        update_balance(ctx.author.id, mise)
        await ctx.send(f"🎉 Gagné {mise} 🪙 !")
    else:
        update_balance(ctx.author.id, -mise)
        await ctx.send(f"😢 Perdu {mise} 🪙")

@bot.command()
async def roulette(ctx, mise: int, choix: str):
    ensure_user(ctx.author.id)
    bal = get_balance(ctx.author.id)
    if mise <= 0 or mise > bal:
        await ctx.send("❌ Mise invalide.")
        return
    choix = choix.lower()
    numero = random.randint(0, 36)
    couleurs = {0: "vert"}
    for i in range(1, 37):
        couleurs[i] = "rouge" if i % 2 else "noir"
    couleur_sortie = couleurs[numero]
    await ctx.send(f"🎡 La bille tombe sur {numero} ({couleur_sortie})")
    gain = 0
    if choix.isdigit() and int(choix) == numero:
        gain = mise * 35
    elif choix in ["rouge", "noir"] and choix == couleur_sortie:
        gain = mise * 2
    if gain > 0:
        update_balance(ctx.author.id, gain)
        await ctx.send(f"🎉 Bravo {ctx.author.mention}, tu gagnes {gain} 🪙 !")
    else:
        update_balance(ctx.author.id, -mise)
        await ctx.send(f"😢 Perdu {mise} 🪙")

@bot.command()
async def guess(ctx, mise: int, nombre: int):
    ensure_user(ctx.author.id)
    if mise <= 0 or mise > get_balance(ctx.author.id):
        await ctx.send("❌ Mise invalide.")
        return
    if nombre < 1 or nombre > 10:
        await ctx.send("❌ Choisis un nombre entre 1 et 10.")
        return
    vrai = random.randint(1, 10)
    if nombre == vrai:
        gain = mise * 5
        update_balance(ctx.author.id, gain)
        await ctx.send(f"🎯 Exact ! Le nombre était {vrai}. Tu gagnes {gain} 🪙")
    else:
        update_balance(ctx.author.id, -mise)
        await ctx.send(f"❌ Faux ! Le nombre était {vrai}. Tu perds {mise} 🪙")

@bot.command()
async def dice(ctx, mise: int, choix: int):
    ensure_user(ctx.author.id)
    if mise <= 0 or mise > get_balance(ctx.author.id):
        await ctx.send("❌ Mise invalide.")
        return
    if choix < 1 or choix > 6:
        await ctx.send("❌ Choisis un nombre entre 1 et 6.")
        return
    result = random.randint(1, 6)
    if choix == result:
        gain = mise * 6
        update_balance(ctx.author.id, gain)
        await ctx.send(f"🎲 Bravo ! Le dé tombe sur {result}. Tu gagnes {gain} 🪙 !")
    else:
        update_balance(ctx.author.id, -mise)
        await ctx.send(f"😢 Le dé tombe sur {result}. Tu perds {mise} 🪙")

# ---------------- BLACKJACK ----------------
@bot.command()
async def blackjack(ctx, mise: int):
    ensure_user(ctx.author.id)
    bal = get_balance(ctx.author.id)
    if mise <= 0 or mise > bal:
        await ctx.send ("❌ Mise invalide.")
        return

    deck = [2,3,4,5,6,7,8,9,10,10,10,10,11]*4
    random.shuffle(deck)
    player = [deck.pop(), deck.pop()]
    dealer = [deck.pop(), deck.pop()]

    CARD_EMOJIS = {2:"2️⃣",3:"3️⃣",4:"4️⃣",5:"5️⃣",6:"6️⃣",7:"7️⃣",8:"8️⃣",9:"9️⃣",10:"🔟",11:"🂡"}

    def hand_to_emoji(hand):
        return " ".join(CARD_EMOJIS.get(card,str(card)) for card in hand)

    def hand_value(hand):
        total = sum(hand)
        aces = hand.count(11)
        while total > 21 and aces:
            total -= 10
            aces -= 1
        return total

    player_total = hand_value(player)
    dealer_total = hand_value(dealer)

    # Vérifier blackjack naturel
    if player_total == 21 and len(player) == 2:
        gain = int(mise * 1.5)
        update_balance(ctx.author.id, gain)
        await ctx.send(f"🃏 Blackjack ! Tu gagnes {gain} 🪙 !")
        return

    await ctx.send(
        f"🃏 Tes cartes: {hand_to_emoji(player)} (Total: {player_total})\n"
        f"Dealer montre: {CARD_EMOJIS[dealer[0]]} ❓"
    )

    # Tour du joueur
    while player_total < 21:
        await ctx.send("Tape 'hit' pour tirer une carte ou 'stand' pour rester.")

        def check(m):
            return m.author == ctx.author and m.content.lower() in ["hit","stand"]

        try:
            msg = await bot.wait_for("message", check=check, timeout=30)
        except asyncio.TimeoutError:
            await ctx.send("⏰ Temps écoulé ! On reste automatiquement.")
            break

        if msg.content.lower() == "hit":
            card = deck.pop()
            player.append(card)
            player_total = hand_value(player)
            await ctx.send(
                f"🃏 Tu tires: {CARD_EMOJIS[card]}\n"
                f"Tes cartes: {hand_to_emoji(player)} (Total: {player_total})"
            )
            if player_total > 21:
                update_balance(ctx.author.id, -mise)
                await ctx.send(f"💥 Tu dépasses 21. Perdu {mise} 🪙")
                return
        else:
            await ctx.send(f"{hand_to_emoji(player)} reste avec Total: {player_total}")
            break

    # Tour du dealer
    await ctx.send(f"🤖 Dealer révèle ses cartes: {hand_to_emoji(dealer)} (Total: {dealer_total})")
    while dealer_total < 17:
        card = deck.pop()
        dealer.append(card)
        dealer_total = hand_value(dealer)
        await ctx.send(
            f"🤖 Dealer tire: {CARD_EMOJIS[card]}\n"
            f"Dealer: {hand_to_emoji(dealer)} (Total: {dealer_total})"
        )
        await asyncio.sleep(1)

    # Résultats
    if player_total > 21:
        update_balance(ctx.author.id, -mise)
        await ctx.send(f"😢 Tu perds {mise} 🪙")
    elif dealer_total > 21 or player_total > dealer_total:
        update_balance(ctx.author.id, mise)
        await ctx.send(f"🎉 Tu gagnes {mise} 🪙 !")
    elif player_total < dealer_total:
        update_balance(ctx.author.id, -mise)
        await ctx.send(f"😢 Tu perds {mise} 🪙")
    else:
        await ctx.send("🤝 Égalité avec le dealer !")

# ---------------- LANCEMENT ----------------
bot.run(TOKEN)
