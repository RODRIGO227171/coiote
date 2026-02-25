# bot_gate.py - Versão FINAL corrigida para rodar local e em container/Railway
# Correções: indentação, screenshot logs sem bot, startup log via post_init

import os
import re
import io
import html
import datetime
import asyncio
import httpx
import csv
from dataclasses import dataclass
from typing import Dict, List, Tuple, Optional, Callable
from urllib.parse import urljoin, urlparse

from telegram import Update, InputFile, Message
from telegram.ext import Application, CommandHandler, ContextTypes, MessageHandler, filters
from telegram.error import TimedOut, BadRequest
from telegram.constants import ParseMode

from playwright.async_api import async_playwright, Browser, Page

# =============================
# Configuração principal
# =============================
TOKEN = "8768731529:AAFO9hgrYtVCpKmqDwwu8RI4weBkJ02uJXs"  # ← SUBSTITUA PELO TOKEN REAL DO SEU BOT
GROUP_ID = -5293701786                     # ID do seu grupo para logs

MAX_BYTES = 2_000_000
MAX_SITES_PER_BATCH = 200

MAX_CONCURRENT_SITES = 10
CONCURRENT_UPDATES = 24

HEADERS = {"User-Agent": "Mozilla/5.0 (compatible; PublicHintsInspector/4.0)"}

PATH_TIERS = [
    ["/"],
    ["/cart", "/checkout", "/payment-methods", "/payments", "/billing"],
    ["/privacy", "/terms", "/shipping", "/returns", "/refund", "/security"],
    ["/contact", "/help", "/faq", "/login", "/signin", "/support"],
    ["/sitemap.xml", "/robots.txt"],
]

# =============================
# Premium emoji IDs
# =============================
PREMIUM_EMOJIS = {
    "1": "5447410659077661506",
    "2": "5282843764451195532",
    "3": "5472250091332993630",
    "4": "5399913388845322366",
    "5": "5251203410396458957",
    "6": "5287684458881756303",
    "7": "5224257782013769471",
    "8": "5231200819986047254",
    "9": "5197269100878907942",
    "10": "5188481279963715781",
    "11": "5231012545799666522",
    "12": "5341715473882955310",
}

def ce(num: str) -> Optional[str]:
    return PREMIUM_EMOJIS.get(str(num))

# =============================
# Helpers Telegram
# =============================
def tg_emoji(emoji_id: Optional[str], fallback: str) -> str:
    if not emoji_id:
        return html.escape(fallback)
    return f'<tg-emoji emoji-id="{emoji_id}">🙂</tg-emoji>'

def build_lines_html(lines: List[Tuple[Optional[str], str, str]]) -> str:
    out = []
    for emoji_id, fallback, text in lines:
        out.append(f"{tg_emoji(emoji_id, fallback)} {html.escape(text)}")
    return "\n".join(out)

async def send_lines(update: Update, lines: List[Tuple[Optional[str], str, str]]) -> Message:
    return await update.effective_message.reply_text(build_lines_html(lines), parse_mode="HTML")

async def edit_lines(msg: Message, lines: List[Tuple[Optional[str], str, str]]):
    await msg.edit_text(build_lines_html(lines), parse_mode="HTML")

# =============================
# Envio de log para grupo
# =============================
async def send_log_to_group(bot, text: str):
    try:
        prefix = f"[{datetime.datetime.now().strftime('%Y-%m-%d %H:%M:%S')}] "
        await bot.send_message(
            chat_id=GROUP_ID,
            text=prefix + text,
            disable_notification=True,
            parse_mode=ParseMode.HTML
        )
    except Exception as e:
        print(f"ERRO AO ENVIAR LOG PARA O GRUPO: {e}")

# =============================
# Renderização bonita do resultado
# =============================
def esc(s: str) -> str:
    return html.escape(s or "")

def yn(ok: bool) -> str:
    return "✅ yes" if ok else "❌ no"

def safe_join(items: List[str], limit: int = 25) -> Tuple[str, int]:
    items = [x for x in items if x]
    short = items[:limit]
    more = max(0, len(items) - len(short))
    return ", ".join(short), more

def render_pretty_result(res: "ScanResult") -> str:
    payment_list = res.payment_hints.split(", ") if res.payment_hints else []
    payment_short, payment_more = safe_join(payment_list, limit=22)

    captcha_list = res.captcha_types.split(", ") if res.captcha_types else []
    captcha_short, captcha_more = safe_join(captcha_list, limit=10)

    plat_list = res.platform_hints.split(", ") if res.platform_hints else []
    plat_short, plat_more = safe_join(plat_list, limit=10)

    extra_list = res.extra_hints.split(", ") if res.extra_hints else []
    extra_short, extra_more = safe_join(extra_list, limit=10)

    lines = []

    lines.append(f'{tg_emoji(ce("1"), "🌐")} <b>{esc(res.url)}</b>')
    lines.append(
        f'{tg_emoji(ce("8"), "📊")} Pages: {res.pages_checked}  |  '
        f'Score: {res.score}  |  Confidence: {esc(res.confidence)}'
    )
    if res.screenshot_taken_from:
        lines.append(f"📸 Screenshot from: /{res.screenshot_taken_from.lstrip('/')}")
    lines.append("")

    lines.append(f'{tg_emoji(ce("5"), "🛡")} <b>Security</b>')
    cf_line = yn(res.cloudflare)
    if res.cloudflare_challenge_hint:
        cf_line += " (challenge hint)"
    lines.append(f'{tg_emoji(ce("4"), "⛈")} Cloudflare: {cf_line}')

    prot_line = yn(res.protection_detected)
    if res.protection_vendors:
        prot_line += f" ({esc(res.protection_vendors)})"
    lines.append(f'{tg_emoji(ce("6"), "🤖")} Bot/JS protection: {prot_line}')

    captcha_line = captcha_short if captcha_short else "❌ none found"
    if captcha_more:
        captcha_line += f" (+{captcha_more} more)"
    lines.append(f'{tg_emoji(ce("11"), "🔍")} Captcha: {esc(captcha_line)}')
    lines.append("")

    lines.append(f'{tg_emoji(ce("7"), "💰")} <b>Payments</b>')
    lines.append(f'{tg_emoji(ce("3"), "💳")} AmEx: {"✅ mentioned" if res.amex_mentioned else "❌ not found"}')

    pay_line = payment_short if payment_short else "❌ none found"
    if payment_more:
        pay_line += f" (+{payment_more} more)"
    lines.append(f'{tg_emoji(ce("7"), "💰")} Providers: {esc(pay_line)}')
    lines.append("")

    lines.append(f'{tg_emoji(ce("12"), "🗂")} <b>Platform</b>')
    plat_line = plat_short if plat_short else "❌ none found"
    if plat_more:
        plat_line += f" (+{plat_more} more)"
    lines.append(f'{tg_emoji(ce("12"), "🗂")} Detected: {esc(plat_line)}')
    lines.append("")

    lines.append(f'{tg_emoji(ce("9"), "✍️")} <b>Notes</b>')
    if res.extra_hints:
        extra_line = extra_short if extra_short else "—"
        if extra_more:
            extra_line += f" (+{extra_more} more)"
        lines.append(f'{esc(extra_line)}')
    if res.notes:
        lines.append(esc(res.notes))
    if (not res.extra_hints) and (not res.notes):
        lines.append("—")

    return "\n".join(lines)

# =============================
# Comando /start
# =============================
async def cmd_start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    u = update.effective_user
    username = u.username or u.first_name or "desconhecido"
    await send_log_to_group(context.bot, f"Usuário <b>{username}</b> (ID {u.id}) iniciou o bot com /start")

    sep = "━━━━━━━━━━━━━━━━━━"
    text = "\n".join([
        f'{tg_emoji(ce("1"), "🌐")} <b>Epstein Hints Checker</b>',
        f'{tg_emoji(ce("9"), "✍️")} <i>Justice for Epstein!!!</i>',
        sep,
        f'{tg_emoji(ce("10"), "🚀")} <b>SCAN</b>',
        f'{tg_emoji(ce("11"), "🔍")} <code>/check &lt;site&gt;</code>  — fast',
        f'{tg_emoji(ce("11"), "🔍")} <code>/checkjs &lt;site&gt;</code> — deep',
        "",
        f'{tg_emoji(ce("12"), "🗂")} <b>BATCH</b>',
        f'{tg_emoji(ce("12"), "🗂")} Envie .txt (1 domínio por linha, máx {MAX_SITES_PER_BATCH})',
        f'{tg_emoji(ce("8"), "📊")} /csv — relatório do último batch',
        sep,
        f'{tg_emoji(ce("5"), "🛡")} <b>WHAT IT DETECTS</b>',
        f'{tg_emoji(ce("4"), "⛈")} Cloudflare/WAF',
        f'{tg_emoji(ce("6"), "🤖")} Bot/JS protection',
        f'{tg_emoji(ce("11"), "🔍")} Captchas',
        f'{tg_emoji(ce("7"), "💰")} Payments/gateways',
        f'{tg_emoji(ce("12"), "🗂")} Platforms',
    ])
    await update.effective_message.reply_text(text, parse_mode="HTML")

# =============================
# Helpers utilitários
# =============================
def normalize_url(url: str) -> str:
    url = (url or "").strip()
    if not url:
        return ""
    if not re.match(r"^https?://", url, re.I):
        url = "https://" + url
    return url.rstrip("/")

def rx_any(patterns: List[str], text: str) -> bool:
    return any(re.search(p, text, re.I) for p in patterns)

def rx_find_hits(weighted_patterns: List[Tuple[str, int]], text: str) -> Tuple[bool, int]:
    score = 0
    matched = False
    for pat, w in weighted_patterns:
        if re.search(pat, text, re.I):
            matched = True
            score += w
    return matched, score

def get_host(u: str) -> str:
    try:
        return (urlparse(u).netloc or "").lower()
    except Exception:
        return ""

def root_domain(host: str) -> str:
    parts = [p for p in host.split(".") if p]
    if len(parts) <= 2:
        return host
    return ".".join(parts[-2:])

# =============================
# Keywords e Patterns (parte grande)
# =============================
SCRIPT_PAYMENT_KEYWORDS = re.compile(
    r"(pay|payment|checkout|billing|card|cc-|gateway|processor|3ds|secure|token|vault|"
    r"klarna|adyen|stripe|paypal|braintree|authorize|worldpay|cybersource|square|affirm|afterpay)",
    re.I,
)

def extract_urls_from_html(base_url: str, html_txt: str) -> List[str]:
    urls = []
    for m in re.finditer(r"""<(script|iframe)[^>]+src=["']([^"']+)["']""", html_txt, re.I):
        urls.append(m.group(2))
    for m in re.finditer(r"""<link[^>]+href=["']([^"']+)["']""", html_txt, re.I):
        urls.append(m.group(1))
    out = []
    for u in urls:
        u = (u or "").strip()
        if not u:
            continue
        out.append(urljoin(base_url + "/", u))
    seen = set()
    res = []
    for u in out:
        if u not in seen:
            seen.add(u)
            res.append(u)
    return res

def payment_like_url(u: str) -> bool:
    return bool(SCRIPT_PAYMENT_KEYWORDS.search(u))

def summarize_external_domains(urls: List[str], base_root: str, only_payment_like: bool = True) -> List[str]:
    hits = []
    for u in urls:
        h = get_host(u)
        if not h:
            continue
        rd = root_domain(h)
        if not rd:
            continue
        if rd == base_root:
            continue
        if (not only_payment_like) or payment_like_url(u) or payment_like_url(rd):
            hits.append(rd)
    return sorted(set(hits))[:20]

AMEX_PATTERNS = [
    r"\bamerican\s*express\b",
    r"\bamex\b",
    r"americanexpress",
    r"amex\.(svg|png|webp)",
    r"accept(s|ed)?\s+amex",
    r"payment\s+methods?.*amex",
]

CAPTCHA_HINTS = {
    "reCAPTCHA": [
        (r"recaptcha/api\.js", 6),
        (r"www\.google\.com/recaptcha", 6),
        (r"\bgrecaptcha\b", 4),
        (r"g-recaptcha", 3),
    ],
    "hCaptcha": [
        (r"hcaptcha\.com/1/api\.js", 6),
        (r"\bhcaptcha\b", 4),
        (r"data-sitekey", 1),
    ],
    "Cloudflare Turnstile": [
        (r"challenges\.cloudflare\.com/turnstile", 8),
        (r"turnstile\.v0", 5),
        (r"\bturnstile\b", 2),
    ],
    "Arkose/FunCaptcha": [
        (r"client-api\.arkoselabs\.com", 8),
        (r"\barkoselabs\b", 4),
        (r"funcaptcha", 4),
    ],
}

CLOUDFLARE_HTML = [
    r"cdn-cgi",
    r"cf-chl-",
    r"cf-browser-verification",
    r"challenges\.cloudflare\.com",
    r"__cf_chl_",
]

CLOUDFLARE_HEADERS = [
    r"^server:\s*cloudflare\b",
    r"^cf-ray:",
    r"^cf-cache-status:",
]

CLOUDFLARE_COOKIES = [
    r"__cf_bm",
    r"cf_clearance",
]

CLOUDFLARE_CHALLENGE_TEXT = [
    r"attention required",
    r"checking your browser",
    r"just a moment",
    r"verify you are human",
]

BOT_PROTECTION_TEXT = [
    r"verify that you're not a robot",
    r"verify you are human",
    r"javascript is disabled",
    r"enable javascript",
    r"we need to verify",
    r"not a robot",
    r"robot check",
    r"unusual traffic",
    r"access denied",
    r"your request has been blocked",
    r"temporarily unavailable",
]

BOT_VENDOR_HINTS = {
    "PerimeterX": [r"perimeterx", r"\bpx-captcha\b", r"_px3|_pxvid|_pxde"],
    "DataDome": [r"datadome", r"captcha\.datadome", r"datadome\.co"],
    "Akamai Bot Manager": [r"\bakama(i|e)\b", r"_abck", r"bm_sz", r"ak_bmsc", r"abck"],
    "Imperva/Incapsula": [r"incapsula", r"imperva", r"visid_incap", r"incap_ses"],
    "Cloudflare Bot Mgmt": [r"cf-bm", r"__cf_bm", r"cf-turnstile"],
    "hCaptcha (vendor hint)": [r"hcaptcha", r"hcaptcha\.com"],
    "reCAPTCHA (vendor hint)": [r"recaptcha", r"google\.com/recaptcha"],
}

PLATFORM_HINTS = {
    "Shopify": [(r"cdn\.shopify\.com", 10), (r"myshopify\.com", 8), (r"\bx-shopify-", 6)],
    "WooCommerce": [(r"woocommerce", 9), (r"wc-ajax", 7)],
    "WordPress": [(r"wp-content/", 4), (r"wp-includes/", 4), (r"content=\"wordpress", 7)],
    "Magento": [(r"magento", 7), (r"mage/cookies", 8), (r"static/version", 6)],
    "BigCommerce": [(r"bigcommerce", 6), (r"cdn\d*\.bigcommerce\.com", 9), (r"stencil", 6)],
    "PrestaShop": [(r"prestashop", 9)],
    "OpenCart": [(r"opencart", 7), (r"index\.php\?route=", 8)],
    "CS-Cart": [(r"cscart", 7), (r"\bdispatch=", 6), (r"tygh", 7)],
    "Wix": [(r"wixsite\.com", 10), (r"wixstatic\.com", 9), (r"\bwix\b", 5)],
    "Squarespace": [(r"squarespace\.com", 10), (r"static\.squarespace\.com", 9)],
    "Webflow": [(r"webflow\.com", 10), (r"data-wf-", 6)],
    "Ecwid": [(r"ecwid\.com", 10), (r"app\.ecwid\.com", 9), (r"x-ecwid", 6)],
    "VTEX": [(r"vteximg\.com\.br", 10), (r"vtexassets\.com", 9), (r"\bvtex\b", 6)],
    "Nuvemshop/TiendaNube": [(r"nuvemshop|tiendanube", 10), (r"cdn\.tiendanube\.com", 9)],
    "Loja Integrada": [(r"lojaintegrada", 10), (r"cdn\.lojaintegrada", 8)],
    "Tray": [(r"traycdn", 9), (r"traycommerce", 8)],
    "Miva Merchant": [(r"merchant2?/merchant\.mvc", 10), (r"store_code=", 6), (r"\bmiva\b", 6)],
    "Salesforce Commerce Cloud": [(r"demandware", 10), (r"dwfrm_", 6), (r"dwcont", 7)],
    "Shopware": [(r"shopware", 10), (r"/bundles/storefront/", 6)],
    "Shift4Shop/3dcart": [(r"3dcart", 10), (r"shift4shop", 10)],
    "Square Online/Weebly": [(r"squareup\.com", 8), (r"weebly\.com", 6)],
}

CARD_FORM_HINTS = [
    (r"autocomplete=\"cc-number\"", 9),
    (r"autocomplete=\"cc-csc\"", 7),
    (r"autocomplete=\"cc-exp\"", 7),
    (r"\bcc_number\b|\bccnum\b|\bcardnumber\b", 7),
    (r"card\s*number", 4),
    (r"cvv|cvc", 4),
    (r"expiration|exp\s*date|mm\s*/\s*yy", 3),
    (r"name\s*on\s*card", 3),
]

PAYMENT_METHODS_TEXT_HINTS = [
    (r"payment\s*methods?", 3),
    (r"we\s*accept", 3),
    (r"visa|mastercard|american\s*express|discover", 2),
]

EXTERNAL_DOMAIN_HINTS = {
    "PayPal (domain)": [(r"paypal\.com|paypalobjects\.com", 8)],
    "Stripe (domain)": [(r"stripe\.com|js\.stripe\.com|checkout\.stripe\.com", 8)],
    "Authorize.Net (domain)": [(r"authorize\.net", 8)],
    "Adyen (domain)": [(r"adyen\.com|checkoutshopper", 8)],
    "Braintree (domain)": [(r"braintreegateway\.com", 8)],
    "Klarna (domain)": [(r"klarna\.com", 6)],
    "Afterpay (domain)": [(r"afterpay|clearpay", 6)],
    "Affirm (domain)": [(r"affirm\.com|cdn1\.affirm", 6)],
}

STRONG_GATEWAY_HINTS = {
    "Stripe": [(r"js\.stripe\.com", 10), (r"checkout\.stripe\.com", 10), (r"stripe-elements|stripe-js", 6), (r"\bstripe\b", 3)],
    "Adyen": [(r"checkoutshopper", 10), (r"adyen\.com", 8), (r"\badyen\b", 4)],
    "PayPal": [(r"paypalobjects\.com", 10), (r"paypal\.com/sdk", 10), (r"\bpaypal\b", 3)],
    "Braintree": [(r"client\.braintreegateway\.com", 10), (r"braintreegateway", 8), (r"\bbraintree\b", 4)],
    "Checkout.com": [(r"\bcheckout\.com\b", 8), (r"\bcko-\b", 6), (r"frames\.js", 6)],
    "Authorize.Net": [(r"authorize\.net", 10), (r"Accept\.js", 10), (r"\bauthorize\.net\b", 4)],
    "Worldpay": [(r"online\.worldpay", 10), (r"worldpay\.com", 8), (r"\bworldpay\b", 4)],
    "Cybersource": [(r"flex\.cybersource", 10), (r"cybersource\.com", 8), (r"\bcybersource\b", 4)],
    "Square": [(r"web-payments-sdk", 10), (r"squareup\.com", 9), (r"\bsquare\b", 3)],
    "Klarna (BNPL)": [(r"klarna-payments", 10), (r"klarna\.com", 9), (r"\bklarna\b", 4)],
    "Affirm (BNPL)": [(r"cdn1\.affirm", 10), (r"affirm\.com", 8), (r"\baffirm\b", 4)],
    "Afterpay/Clearpay (BNPL)": [(r"static\.afterpay", 10), (r"\bafterpay\b|\bclearpay\b", 5)],
    "Mercado Pago": [(r"api\.mercadopago\.com", 10), (r"secure\.mercadopago", 9), (r"\bmercado\s*pago\b", 6), (r"mercadopago", 5)],
    "PagSeguro": [(r"pagseguro\.uol\.com\.br", 10), (r"stc\.pagseguro", 10), (r"\bpagseguro\b", 5)],
    "Pagar.me": [(r"api\.pagar\.me|api\.pagar\.me", 10), (r"\bpagar\.?me\b", 6), (r"pagarme", 6)],
    "Cielo": [(r"api\.cielo", 10), (r"cieloecommerce", 9), (r"cielo\.com\.br", 8), (r"\bcielo\b", 4)],
    "Rede": [(r"userede\.com\.br", 10), (r"\berede\b", 9), (r"redecard", 8)],
    "Getnet": [(r"getnet\.com\.br", 10), (r"\bgetnet\b", 5)],
    "EBANX": [(r"ebanx\.com", 10), (r"\bebanx\b", 5)],
}

WEAK_GATEWAY_KEYWORDS = [
    "Amazon Pay", "Apple Pay", "Google Pay", "SagePay", "Opayo", "Verifone", "2Checkout", "Avangate",
    "Global Payments", "Fiserv", "First Data", "Payeezy", "TSYS", "Elavon", "FIS", "NCR", "ACI Worldwide",
    "BlueSnap", "PaymentCloud", "NMI", "PayJunction", "WePay", "Dwolla", "Paysafe", "Skrill", "Neteller",
    "Payoneer", "Wise", "Revolut Pay", "GoCardless", "Zuora", "Chargebee", "Recurly",
    "Kount", "Riskified", "Signifyd", "Forter", "Sift", "ClearSale", "NoFraud",
    "CardinalCommerce", "3D Secure", "Click to Pay",
    "Worldline", "Ingenico", "Ogone", "Nets", "Swedbank Pay", "Bambora", "Viva Wallet", "Trustly",
    "iDEAL", "Sofort", "Giropay", "Bancontact", "EPS", "Przelewy24",
    "Paytrail", "Boku", "Paysend", "Paysera", "SumUp", "Zettle",
    "MultiSafepay", "Buckaroo", "Payplug", "HiPay", "Lyra", "Monext", "PayZen",
    "SIPS", "Atos Payments", "Barclaycard ePDQ", "SecureTrading", "Ecommpay",
    "Emerchantpay", "Wirecard", "Concardis",
    "dLocal", "Rapyd", "PayU Latam", "Prisma", "TodoPago", "PagoFacil", "Rapipago",
    "OpenPay", "Conekta", "Clip", "Kushki", "PlacetoPay", "Wompi", "Paymentez", "Niubiz",
    "Culqi", "Nequi", "PSE", "SPEI", "OXXO Pay", "Boleto", "Pix",
    "Stone", "Ton", "Iugu", "Asaas", "Moip", "Wirecard BR", "PagBank", "Gerencianet", "PJBank",
    "PicPay", "Ame Digital", "99Pay", "Banco Inter", "Itaú Shopline",
    "Paymee", "Zoop", "Vindi", "Braspag", "Dock", "Conductor", "Cora",
    "Paystack", "Flutterwave", "Interswitch", "Cellulant", "M-Pesa", "Airtel Money", "MTN MoMo",
    "Network International", "Telr", "PayTabs", "HyperPay", "Tap Payments",
    "Fawry", "Paymob", "Opay", "Pesapal",
    "Razorpay", "Paytm", "Cashfree", "CCAvenue", "BillDesk", "Instamojo", "PhonePe", "UPI",
    "PayMongo", "Dragonpay", "Gcash", "GrabPay", "ShopeePay", "TrueMoney",
    "Alipay", "WeChat Pay", "UnionPay", "JCB", "KakaoPay", "Naver Pay",
    "POLi", "eWAY", "Tyro", "Windcave", "Zip Money",
]

def build_weak_gateway_hints(keywords: list[str], weight: int = 2) -> dict[str, list[tuple[str, int]]]:
    hints = {}
    for name in keywords:
        pat = re.escape(name.lower()).replace(r"\ ", r"\s*")
        regex = rf"(?:\b|_){pat}(?:\b|_)"
        hints[name] = [(regex, weight)]
    return hints

GATEWAY_HINTS = {}
GATEWAY_HINTS.update(STRONG_GATEWAY_HINTS)
GATEWAY_HINTS.update(build_weak_gateway_hints(WEAK_GATEWAY_KEYWORDS, weight=2))

# =============================
# Estrutura de resultado
# =============================
@dataclass
class ScanResult:
    url: str
    pages_checked: int
    amex_mentioned: bool
    cloudflare: bool
    cloudflare_challenge_hint: bool
    protection_detected: bool
    protection_vendors: str
    captcha_detected: bool
    captcha_types: str
    payment_hints: str
    platform_hints: str
    extra_hints: str
    confidence: str
    score: int
    notes: str
    screenshot_bytes: Optional[bytes] = None
    screenshot_taken_from: Optional[str] = None

# =============================
# Cliente HTTP global
# =============================
HTTP_CLIENT: Optional[httpx.AsyncClient] = None
_HTTP_LOCK = asyncio.Lock()

async def get_http_client() -> httpx.AsyncClient:
    global HTTP_CLIENT
    async with _HTTP_LOCK:
        if HTTP_CLIENT is None:
            HTTP_CLIENT = httpx.AsyncClient(
                follow_redirects=True,
                limits=httpx.Limits(max_connections=80, max_keepalive_connections=40),
                timeout=httpx.Timeout(15.0),
                headers=HEADERS,
            )
        return HTTP_CLIENT

# =============================
# Playwright global
# =============================
PW_LOCK = asyncio.Lock()
PW = None
PW_BROWSER: Optional[Browser] = None

async def get_browser() -> Browser:
    global PW, PW_BROWSER
    async with PW_LOCK:
        if PW_BROWSER is None:
            PW = await async_playwright().start()
            PW_BROWSER = await PW.chromium.launch(headless=True)
        return PW_BROWSER

async def shutdown_playwright():
    global PW, PW_BROWSER
    async with PW_LOCK:
        if PW_BROWSER is not None:
            await PW_BROWSER.close()
            PW_BROWSER = None
        if PW is not None:
            await PW.stop()
            PW = None

# =============================
# Funções de fetch
# =============================
async def fetch_public_async(url: str) -> Tuple[str, str, str, int, str, str]:
    try:
        client = await get_http_client()
        r = await client.get(url)
        status = r.status_code
        final_url = str(r.url)
        content = r.content[:MAX_BYTES]
        html_txt = content.decode("utf-8", errors="ignore").lower()
        headers_joined = "\n".join(f"{k}: {v}" for k, v in r.headers.items()).lower()
        cookie_names = " ".join(r.cookies.keys()).lower()
        return html_txt, headers_joined, cookie_names, status, final_url, ""
    except Exception as e:
        return "", "", "", 0, "", str(e)[:160]

async def fetch_rendered_html(url: str, max_wait_ms: int = 12000) -> Tuple[str, List[str], str]:
    try:
        browser = await get_browser()
        ctx = await browser.new_context(user_agent=HEADERS["User-Agent"])
        page = await ctx.new_page()
        net_urls = []

        page.on("request", lambda req: net_urls.append(req.url) if len(net_urls) < 300 else None)

        await page.goto(url, wait_until="domcontentloaded", timeout=max_wait_ms)
        await page.wait_for_timeout(2000)

        content = await page.content()
        await ctx.close()
        return content.lower(), net_urls, ""
    except Exception as e:
        return "", [], str(e)[:160]

# =============================
# Detectores
# =============================
def detect_cloudflare(html_txt: str, headers_joined: str, cookie_names: str, status_code: int) -> Tuple[bool, bool, int]:
    score = 0
    cf = False
    challenge = False
    if rx_any(CLOUDFLARE_HEADERS, headers_joined):
        cf = True
        score += 8
    if rx_any(CLOUDFLARE_COOKIES, cookie_names):
        cf = True
        score += 6
    if rx_any(CLOUDFLARE_HTML, html_txt):
        cf = True
        score += 6
    if status_code in (403, 429, 503) and rx_any(CLOUDFLARE_CHALLENGE_TEXT, html_txt):
        challenge = True
        cf = True
        score += 10
    return cf, challenge, score

def detect_bot_protection(html_txt: str, headers_joined: str, cookie_names: str, status_code: int) -> Tuple[bool, List[str], int]:
    score = 0
    detected = False
    vendors = []
    if status_code == 202:
        detected = True
        score += 10
    if rx_any(BOT_PROTECTION_TEXT, html_txt):
        detected = True
        score += 8
    for vname, pats in BOT_VENDOR_HINTS.items():
        if rx_any(pats, html_txt) or rx_any(pats, cookie_names) or rx_any(pats, headers_joined):
            vendors.append(vname)
            detected = True
            score += 3
    return detected, sorted(set(vendors)), min(14, score)

def detect_platforms(html_txt: str, headers_joined: str) -> Tuple[List[str], int]:
    found = []
    score = 0
    blob = html_txt + "\n" + headers_joined
    for pname, pats in PLATFORM_HINTS.items():
        hit, sc = rx_find_hits(pats, blob)
        if hit:
            found.append(pname)
            score += min(12, sc)
    return sorted(set(found)), min(18, score)

def detect_generic_payment_form(html_txt: str) -> Tuple[bool, int]:
    hit, sc = rx_find_hits(CARD_FORM_HINTS, html_txt)
    return hit, min(12, sc)

def detect_payment_methods_text(html_txt: str) -> Tuple[bool, int]:
    hit, sc = rx_find_hits(PAYMENT_METHODS_TEXT_HINTS, html_txt)
    return hit, min(8, sc)

def detect_external_domains(html_txt: str) -> Tuple[List[str], int]:
    found = []
    score = 0
    for name, pats in EXTERNAL_DOMAIN_HINTS.items():
        hit, sc = rx_find_hits(pats, html_txt)
        if hit:
            found.append(name)
            score += sc
    return sorted(set(found)), min(12, score)

# =============================
# Motor de scan - CORRIGIDO
# =============================
async def scan_one_site(
    raw_url: str,
    use_js: bool = False,
    progress_callback: Optional[Callable[[str], asyncio.Future]] = None,
) -> ScanResult:
    base_url = normalize_url(raw_url)
    if not base_url:
        return ScanResult(raw_url, 0, False, False, False, False, "", False, "", "", "", "", "low", 0, "empty url", None, None)

    alt_http_url = ""
    if base_url.startswith("https://"):
        alt_http_url = "http://" + base_url[len("https://"):]

    base_host = get_host(base_url)
    base_root = root_domain(base_host)

    amex = False
    captcha_found = set()
    payment_found = set()
    platform_found = set()
    extra_found = set()

    total_score = 0
    cf_detected_any = False
    cf_challenge_any = False
    protection_any = False
    protection_vendors_found = set()

    errors = 0
    fail_samples = []
    status_debug = []
    pages_ok = 0
    pages_total = sum(len(t) for t in PATH_TIERS)

    async def progress(msg: str):
        if progress_callback:
            await progress_callback(msg)

    async def analyze_blob(curr_base: str, html_txt: str, hdrs: str = "", cookies: str = "", status: int = 200, final_url: str = ""):
        nonlocal amex, total_score, cf_detected_any, cf_challenge_any, protection_any
        nonlocal protection_vendors_found, captcha_found, payment_found, platform_found, extra_found

        prot, vendors, prot_score = detect_bot_protection(html_txt, hdrs, cookies, status)
        if prot:
            protection_any = True
            total_score += prot_score
            captcha_found.add("Bot protection / JS challenge")
            for v in vendors:
                protection_vendors_found.add(v)

        cf, challenge, cf_score = detect_cloudflare(html_txt, hdrs, cookies, status)
        if cf:
            cf_detected_any = True
        if challenge:
            cf_challenge_any = True
        total_score += min(12, cf_score)

        plats, plat_score = detect_platforms(html_txt, hdrs)
        for p in plats:
            platform_found.add(p)
        total_score += plat_score

        if rx_any(AMEX_PATTERNS, html_txt):
            amex = True
            total_score += 2

        captcha_score_local = 0
        for cname, pats in CAPTCHA_HINTS.items():
            hit, sc = rx_find_hits(pats, html_txt)
            if hit:
                captcha_found.add(cname)
                captcha_score_local += sc
        if captcha_score_local:
            total_score += min(12, captcha_score_local)

        ext_domains, ext_score = detect_external_domains(html_txt)
        for d in ext_domains:
            payment_found.add(d)
        total_score += ext_score

        pay_score_local = 0
        for gname, pats in GATEWAY_HINTS.items():
            hit, sc = rx_find_hits(pats, html_txt)
            if hit:
                payment_found.add(gname)
                pay_score_local += sc
        if pay_score_local:
            total_score += min(18, pay_score_local)

        form_hit, form_score = detect_generic_payment_form(html_txt)
        if form_hit:
            extra_found.add("Card form detected (generic fields)")
            total_score += form_score

        pm_hit, pm_score = detect_payment_methods_text(html_txt)
        if pm_hit:
            extra_found.add("Payment methods text detected (generic)")
            total_score += pm_score

        asset_urls = extract_urls_from_html(curr_base, html_txt)
        payment_assets = [u for u in asset_urls if payment_like_url(u)]
        if payment_assets:
            for dom in summarize_external_domains(payment_assets, root_domain(get_host(curr_base)), only_payment_like=True):
                extra_found.add(f"Payment-like external domain: {dom}")
                total_score += 1

            for u in payment_assets[:2]:
                a_html, a_hdrs, a_cookies, a_status, a_final, a_err = await fetch_public_async(u)
                if a_status and a_html:
                    payment_found.add("Asset scan (payment-like)")
                    asset_score_local = 0
                    for gname, pats in GATEWAY_HINTS.items():
                        hit, sc = rx_find_hits(pats, a_html)
                        if hit:
                            payment_found.add(gname + " (via asset)")
                            asset_score_local += sc
                    if asset_score_local:
                        total_score += min(12, asset_score_local)

    async def run_http_scan(curr_base: str):
        nonlocal errors, pages_ok, status_debug, fail_samples

        for tier_idx, tier in enumerate(PATH_TIERS, start=1):
            tasks = []
            for path in tier:
                url = urljoin(curr_base + "/", path.lstrip("/"))
                tasks.append((path, asyncio.create_task(fetch_public_async(url))))

            for fut in asyncio.as_completed([t for _, t in tasks]):
                path = next((p for p, t in tasks if t is fut), "?")
                html_txt, hdrs, cookies, status, final_url, err_short = await fut

                if status == 0:
                    errors += 1
                    if err_short and len(fail_samples) < 3:
                        fail_samples.append(err_short)
                    continue

                pages_ok += 1
                if len(status_debug) < 12:
                    status_debug.append(f"{path}:{status}")

                await analyze_blob(curr_base, html_txt, hdrs, cookies, status, final_url)
                await progress(f"Checking… {pages_ok}/{pages_total} pages (tier {tier_idx}/{len(PATH_TIERS)})")

            if total_score >= 28 or (payment_found and platform_found) or len(payment_found) >= 2:
                break

    async def run_js_scan(curr_base: str) -> Tuple[Optional[bytes], Optional[str]]:
        nonlocal errors, pages_ok, status_debug, fail_samples, total_score

        screenshot_bytes = None
        screenshot_taken_from = None

        js_paths = ["/", "/cart", "/checkout"]
        for i, path in enumerate(js_paths, start=1):
            url = urljoin(curr_base + "/", path.lstrip("/"))
            await progress(f"Rendering… {i}/{len(js_paths)} ({path})")

            r_html, net_urls, err = await fetch_rendered_html(url)
            if not r_html:
                errors += 1
                if err and len(fail_samples) < 3:
                    fail_samples.append("JS " + err)
                continue

            pages_ok += 1
            if len(status_debug) < 12:
                status_debug.append(f"{path}:rendered")

            ext = summarize_external_domains(net_urls, base_root, only_payment_like=True)
            for dom in ext[:12]:
                extra_found.add(f"Payment-like external domain: {dom}")
                total_score += 1

            await analyze_blob(curr_base, r_html, "", "", 200, url)

            # Screenshot - CORRIGIDO: sem bot, apenas print
            if screenshot_bytes is None and path in ["/checkout", "/cart", "/"]:
                try:
                    browser = await get_browser()
                    ctx = await browser.new_context(user_agent=HEADERS["User-Agent"])
                    page = await ctx.new_page()
                    await page.goto(url, wait_until="domcontentloaded", timeout=15000)
                    await page.wait_for_timeout(3000)
                    screenshot_bytes = await page.screenshot(
                        type="jpeg",
                        quality=80,
                        full_page=True,
                        timeout=15000
                    )
                    screenshot_taken_from = path
                    print(f"[DEBUG] Screenshot capturado de {path} - tamanho: {len(screenshot_bytes)/1024/1024:.2f} MB")
                    await ctx.close()
                except Exception as e:
                    print(f"[DEBUG] Erro ao capturar screenshot de {path}: {e}")

        return screenshot_bytes, screenshot_taken_from

    screenshot_bytes = None
    screenshot_taken_from = None

    if use_js:
        screenshot_bytes, screenshot_taken_from = await run_js_scan(base_url)
    else:
        await run_http_scan(base_url)

    if pages_ok == 0 and alt_http_url:
        if use_js:
            screenshot_bytes, screenshot_taken_from = await run_js_scan(alt_http_url)
        else:
            await run_http_scan(alt_http_url)
        if pages_ok > 0:
            base_url = alt_http_url

    confidence = "low"
    if total_score >= 48:
        confidence = "high"
    elif total_score >= 22:
        confidence = "medium"
    if protection_any and confidence == "low":
        confidence = "medium"

    notes_parts = []
    if errors:
        notes_parts.append(f"{errors} page(s) failed")
    if fail_samples:
        notes_parts.append("fail_examples=" + " || ".join(fail_samples))
    if status_debug:
        notes_parts.append("status=" + ",".join(status_debug))
    notes = " | ".join(notes_parts)

    return ScanResult(
        url=base_url,
        pages_checked=pages_ok,
        amex_mentioned=amex,
        cloudflare=cf_detected_any,
        cloudflare_challenge_hint=cf_challenge_any,
        protection_detected=protection_any,
        protection_vendors=", ".join(sorted(protection_vendors_found)),
        captcha_detected=bool(captcha_found),
        captcha_types=", ".join(sorted(captcha_found)),
        payment_hints=", ".join(sorted(payment_found)),
        platform_hints=", ".join(sorted(platform_found)),
        extra_hints=", ".join(sorted(extra_found)),
        confidence=confidence,
        score=total_score,
        notes=notes,
        screenshot_bytes=screenshot_bytes,
        screenshot_taken_from=screenshot_taken_from,
    )

# =============================
# Envio do resultado com screenshot
# =============================
async def send_result_with_screenshot(update: Update, res: ScanResult, progress_msg: Message):
    text = render_pretty_result(res)

    if res.screenshot_bytes:
        try:
            bio = io.BytesIO(res.screenshot_bytes)
            bio.name = f"screenshot_{res.screenshot_taken_from or 'page'}.jpg"

            if len(res.screenshot_bytes) > 8_000_000:
                await update.effective_message.reply_document(
                    document=InputFile(bio),
                    caption=text,
                    parse_mode="HTML"
                )
            else:
                await update.effective_message.reply_photo(
                    photo=InputFile(bio),
                    caption=text,
                    parse_mode="HTML"
                )

            try:
                await progress_msg.delete()
            except Exception as del_err:
                await send_log_to_group(update.effective_chat.bot, f"Erro ao deletar progresso após envio: {del_err}")
            return
        except TimedOut as to_err:
            await send_log_to_group(update.effective_chat.bot, f"Timeout no envio da screenshot: {to_err}")
            text += "\n\n<i>Timeout ao enviar screenshot (rede lenta ou limite do Telegram)</i>"
        except Exception as e:
            await send_log_to_group(update.effective_chat.bot, f"Erro ao enviar screenshot: {e}")
            text += f"\n\n<i>Erro ao enviar screenshot: {str(e)[:80]}</i>"

    try:
        await progress_msg.edit_text(text, parse_mode="HTML")
    except BadRequest as br_err:
        if "Message to edit not found" in str(br_err):
            await send_log_to_group(update.effective_chat.bot, "Mensagem de progresso não encontrada - enviando nova")
            await update.effective_message.reply_text(text, parse_mode="HTML")
        else:
            await send_log_to_group(update.effective_chat.bot, f"Erro no fallback edit: {br_err}")
    except Exception as e:
        await send_log_to_group(update.effective_chat.bot, f"Erro no fallback: {e}")
        await update.effective_message.reply_text(text, parse_mode="HTML")

# =============================
# Comandos /check e /checkjs
# =============================
_last_batch_results: Dict[int, List[ScanResult]] = {}

async def cmd_check(update: Update, context: ContextTypes.DEFAULT_TYPE):
    u = update.effective_user
    username = u.username or u.first_name or "desconhecido"
    if not context.args:
        await send_lines(update, [(ce("11"), "🔍", "Usage: /check example.com")])
        return

    target = context.args[0]
    await send_log_to_group(context.bot, f"<b>{username}</b> (ID {u.id}) → /check <code>{target}</code>")

    progress_msg = await send_lines(update, [(ce("11"), "🔍", "Checking…")])
    last_edit = 0.0

    async def progress_callback(txt: str):
        nonlocal last_edit
        now = asyncio.get_event_loop().time()
        if now - last_edit > 1.0:
            last_edit = now
            await edit_lines(progress_msg, [(ce("11"), "🔍", txt)])

    res = await scan_one_site(target, use_js=False, progress_callback=progress_callback)
    await send_result_with_screenshot(update, res, progress_msg)

    conf = res.confidence.upper()
    score = res.score
    await send_log_to_group(context.bot, f"Resultado /check <code>{target}</code> → Confidence: <b>{conf}</b> | Score: {score} | CF: {yn(res.cloudflare)} | Pagamentos: {res.payment_hints[:80]}{'...' if len(res.payment_hints)>80 else ''}")

async def cmd_checkjs(update: Update, context: ContextTypes.DEFAULT_TYPE):
    u = update.effective_user
    username = u.username or u.first_name or "desconhecido"
    if not context.args:
        await send_lines(update, [(ce("11"), "🔍", "Usage: /checkjs example.com")])
        return

    target = context.args[0]
    await send_log_to_group(context.bot, f"<b>{username}</b> (ID {u.id}) → /checkjs <code>{target}</code>")

    progress_msg = await send_lines(update, [(ce("11"), "🔍", "Starting deep JS scan…")])
    last_edit = 0.0

    async def progress_callback(txt: str):
        nonlocal last_edit
        now = asyncio.get_event_loop().time()
        if now - last_edit > 1.0:
            last_edit = now
            await edit_lines(progress_msg, [(ce("11"), "🔍", txt)])

    res = await scan_one_site(target, use_js=True, progress_callback=progress_callback)
    await send_result_with_screenshot(update, res, progress_msg)

    conf = res.confidence.upper()
    score = res.score
    await send_log_to_group(context.bot, f"Resultado /checkjs <code>{target}</code> → Confidence: <b>{conf}</b> | Score: {score} | CF: {yn(res.cloudflare)} | Pagamentos: {res.payment_hints[:80]}{'...' if len(res.payment_hints)>80 else ''}")

def results_to_csv_bytes(results: List[ScanResult]) -> bytes:
    bio = io.BytesIO()
    writer = csv.writer(bio)
    writer.writerow(["url", "confidence", "score", "pages_checked", "amex_mentioned", "cloudflare", "cloudflare_challenge_hint", "protection_detected", "protection_vendors", "captcha_types", "payment_hints", "platform_hints", "extra_hints", "notes"])
    for res in results:
        writer.writerow([res.url, res.confidence, res.score, res.pages_checked, res.amex_mentioned, res.cloudflare, res.cloudflare_challenge_hint, res.protection_detected, res.protection_vendors, res.captcha_types, res.payment_hints, res.platform_hints, res.extra_hints, res.notes])
    return bio.getvalue()

async def cmd_csv(update: Update, context: ContextTypes.DEFAULT_TYPE):
    u = update.effective_user
    username = u.username or u.first_name or "desconhecido"
    await send_log_to_group(context.bot, f"<b>{username}</b> (ID {u.id}) → /csv")

    chat_id = update.effective_chat.id
    results = _last_batch_results.get(chat_id)
    if not results:
        await send_lines(update, [(ce("12"), "🗂", "No recent batch. Send a .txt with sites first.")])
        return

    csv_bytes = results_to_csv_bytes(results)
    bio = io.BytesIO(csv_bytes)
    bio.name = "report.csv"
    await update.effective_message.reply_document(
        document=InputFile(bio),
        caption="📊 report.csv"
    )

def parse_sites_from_text(text: str) -> List[str]:
    sites = []
    for line in (text or "").splitlines():
        line = line.strip()
        if not line or line.startswith("#"):
            continue
        sites.append(line)

    seen = set()
    out = []
    for s in sites:
        if s not in seen:
            seen.add(s)
            out.append(s)
    return out

async def handle_document(update: Update, context: ContextTypes.DEFAULT_TYPE):
    u = update.effective_user
    username = u.username or u.first_name or "desconhecido"
    doc = update.effective_message.document
    if not doc:
        return

    filename = (doc.file_name or "").lower()
    if not filename.endswith(".txt"):
        await send_lines(update, [(ce("12"), "🗂", "Send a .txt file (1 domain per line).")])
        return

    if doc.file_size and doc.file_size > 1024 * 1024:
        await send_lines(update, [(ce("12"), "🗂", "File too large. Keep under 1MB.")])
        return

    await send_log_to_group(context.bot, f"<b>{username}</b> (ID {u.id}) enviou arquivo batch: <code>{filename}</code> ({doc.file_size or '?'} bytes)")

    progress_msg = await send_lines(update, [(ce("10"), "🚀", "Batch: starting…")])

    tg_file = await doc.get_file()
    file_bytes = await tg_file.download_as_bytearray()
    text = file_bytes.decode("utf-8", errors="ignore")
    sites = parse_sites_from_text(text)

    if not sites:
        await edit_lines(progress_msg, [(ce("10"), "🚀", "The .txt is empty.")])
        return

    if len(sites) > MAX_SITES_PER_BATCH:
        sites = sites[:MAX_SITES_PER_BATCH]

    results = []
    done = 0
    total = len(sites)

    sem = asyncio.Semaphore(MAX_CONCURRENT_SITES)
    last_edit = 0.0

    async def scan_site(site: str) -> ScanResult:
        async with sem:
            return await scan_one_site(site, use_js=False)

    tasks = [asyncio.create_task(scan_site(s)) for s in sites]
    for fut in asyncio.as_completed(tasks):
        res = await fut
        results.append(res)
        done += 1
        now = asyncio.get_event_loop().time()
        if now - last_edit > 1.0:
            last_edit = now
            await edit_lines(progress_msg, [(ce("10"), "🚀", f"Batch: {done}/{total} sites ({int(done / total * 100)}%)")])

    chat_id = update.effective_chat.id
    _last_batch_results[chat_id] = results

    high = sum(1 for r in results if r.confidence == "high")
    med = sum(1 for r in results if r.confidence == "medium")
    low = sum(1 for r in results if r.confidence == "low")

    await edit_lines(progress_msg, [
        (ce("10"), "🚀", f"Batch done ({len(results)} sites)"),
        (ce("8"),  "📊", f"Confidence: high={high}, medium={med}, low={low}"),
        (ce("12"), "🗂", "Use /csv to download the report."),
    ])

    await send_log_to_group(context.bot, f"Batch concluído ({len(results)} sites) por <b>{username}</b>\n→ High: {high} | Medium: {med} | Low: {low}")

# =============================
# Shutdown
# =============================
async def _post_shutdown(app: Application):
    global HTTP_CLIENT
    if HTTP_CLIENT is not None:
        await HTTP_CLIENT.aclose()
        HTTP_CLIENT = None
    await shutdown_playwright()

# =============================
# Log inicial no grupo
# =============================
async def post_init(application: Application) -> None:
    try:
        await send_log_to_group(application.bot, "🤖 Bot iniciado no servidor (Railway/Container)")
    except Exception as e:
        print(f"Erro no post_init log: {e}")

# =============================
# Main - indentação perfeita
# =============================
def main():
    if not TOKEN or TOKEN == "SEU_TOKEN_AQUI_DIRETO_NO_CODIGO":
        print("ERRO: Substitua o TOKEN no código antes de rodar!")
        return

    print("Iniciando bot no modo servidor...")

    app = Application.builder() \
        .token(TOKEN) \
        .concurrent_updates(CONCURRENT_UPDATES) \
        .post_init(post_init) \
        .post_shutdown(_post_shutdown) \
        .build()

    app.add_handler(CommandHandler("start", cmd_start))
    app.add_handler(CommandHandler("check", cmd_check))
    app.add_handler(CommandHandler("checkjs", cmd_checkjs))
    app.add_handler(CommandHandler("csv", cmd_csv))
    app.add_handler(MessageHandler(filters.Document.ALL, handle_document))

    app.run_polling(allowed_updates=Update.ALL_TYPES)

if __name__ == "__main__":
    main()
