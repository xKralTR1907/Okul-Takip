import datetime
import json
import os
import queue
import re
import threading
import tkinter as tk
import urllib.request
import webbrowser
from concurrent.futures import ThreadPoolExecutor
from html.parser import HTMLParser
from urllib.parse import urljoin
from tkinter import messagebox, ttk

# ----------------------------------------------------------------- ayarlar
HAFTA = 14
RENK_BOS = "#eceff4"
RENK_YESIL = "#2fb457"
RENK_KIRMIZI = "#e5484d"
ARKA = "#f6f7f9"
KART = "#ffffff"
METIN = "#1d2330"
GRI = "#7a8394"
CIZGI = "#d9dde5"

YEMEK_URL = "https://www.uludag.edu.tr/yemek"
ANA_URL = "https://www.uludag.edu.tr/tr/iibf"

KLASOR = os.path.dirname(os.path.abspath(__file__))


def dosya_yolu(ad):
    if os.access(KLASOR, os.W_OK):
        return os.path.join(KLASOR, ad)
    return os.path.join(os.path.expanduser("~"), ad)


KAYIT = dosya_yolu("devamsizlik_kayit.json")
ONBELLEK = dosya_yolu("yemek_onbellek.json")
DUYURU_ONBELLEK = dosya_yolu("duyuru_onbellek.json")

GUNLER = ["Pazartesi", "Salı", "Çarşamba", "Perşembe", "Cuma", "Cumartesi", "Pazar"]
AYLAR = ["Ocak", "Şubat", "Mart", "Nisan", "Mayıs", "Haziran", "Temmuz",
         "Ağustos", "Eylül", "Ekim", "Kasım", "Aralık"]

ALERJENLER = [
    "1 - Glüten içeren tahıllar", "2 - Kabuklular", "3 - Yumurta", "4 - Süt ve süt ürünleri",
    "5 - Balık", "6 - Hardal", "7 - Yerfıstığı", "8 - Soya", "9 - Kereviz", "10 - Acı bakla",
    "11 - Sert kabuklu meyveler (ceviz, fındık vb.)", "12 - Kükürt dioksit ve sülfitler",
    "13 - Yumuşakçalar", "14 - Susam",
]


# ============================================================ DEVAMSIZLIK
def bos_kayit():
    return {"name": "", "st": [0] * HAFTA}


class Satir:
    def __init__(self, app, veri, r):
        self.app = app
        self.veri = veri
        parent = app.grid_frame

        self.var = tk.StringVar(value=veri["name"])
        self.entry = tk.Entry(parent, textvariable=self.var, width=24, font=("Segoe UI", 11),
                              relief="solid", bd=1, bg="white", fg=METIN, highlightthickness=0)
        self.entry.grid(row=r, column=0, padx=(0, 10), pady=4, ipady=5, sticky="w")

        self.kutular = []
        for i in range(HAFTA):
            k = tk.Label(parent, width=4, height=2, bg=RENK_BOS, relief="solid", bd=1,
                         cursor="hand2")
            k.bind("<Button-1>", lambda e, i=i: self.tikla(i))
            k.grid(row=r, column=i + 1, padx=3, pady=4)
            self.kutular.append(k)

        self.sayac = tk.Label(parent, text="", bg=ARKA, fg=GRI, font=("Segoe UI", 10),
                              width=14, anchor="w")
        self.sayac.grid(row=r, column=HAFTA + 1, padx=(8, 0))

        self.sil_btn = tk.Button(parent, text="✕", command=self.sil, bd=0, bg=ARKA, fg=GRI,
                                 activebackground=ARKA, cursor="hand2", font=("Segoe UI", 11))
        self.sil_btn.grid(row=r, column=HAFTA + 2, padx=(4, 0))

        self.var.trace_add("write", self.yazildi)
        self.goster()
        self.yenile()

    def dolu_mu(self):
        return bool(self.veri["name"].strip())

    def goster(self):
        for w in self.kutular + [self.sayac, self.sil_btn]:
            if self.dolu_mu():
                w.grid()
            else:
                w.grid_remove()

    def yenile(self):
        yok = 0
        for k, v in zip(self.kutular, self.veri["st"]):
            k.config(bg=RENK_YESIL if v == 1 else RENK_KIRMIZI if v == 2 else RENK_BOS)
            if v == 2:
                yok += 1
        self.sayac.config(text=f"Devamsız: {yok}/{HAFTA}")

    def tikla(self, i):
        self.veri["st"][i] = (self.veri["st"][i] + 1) % 3
        self.yenile()
        self.app.kaydet()

    def yazildi(self, *_):
        self.veri["name"] = self.var.get()
        self.goster()
        if self.dolu_mu() and self.app.satirlar[-1] is self:
            self.app.yeni_bos_satir()
        self.app.kaydet()

    def sil(self):
        if messagebox.askyesno("Dersi sil", f'"{self.veri["name"]}" dersi silinsin mi?'):
            self.app.satir_sil(self)


class DevamsizlikSekmesi:
    def __init__(self, parent):
        parent.configure(bg=ARKA)
        tk.Label(parent, text="Devamsızlık Takibi", font=("Segoe UI", 15, "bold"),
                 bg=ARKA, fg=METIN).pack(anchor="w", padx=20, pady=(16, 0))
        tk.Label(parent, text="Ders adını yaz → 1 tık: girdim (yeşil) · 2 tık: gitmedim (kırmızı) · 3 tık: sıfırla",
                 font=("Segoe UI", 10), bg=ARKA, fg=GRI).pack(anchor="w", padx=20, pady=(0, 12))

        kap = tk.Frame(parent, bg=ARKA)
        kap.pack(fill="both", expand=True, padx=20, pady=(0, 16))
        self.canvas = tk.Canvas(kap, bg=ARKA, highlightthickness=0)
        ysb = tk.Scrollbar(kap, orient="vertical", command=self.canvas.yview)
        xsb = tk.Scrollbar(kap, orient="horizontal", command=self.canvas.xview)
        self.canvas.configure(yscrollcommand=ysb.set, xscrollcommand=xsb.set)
        ysb.pack(side="right", fill="y")
        xsb.pack(side="bottom", fill="x")
        self.canvas.pack(side="left", fill="both", expand=True)

        self.grid_frame = tk.Frame(self.canvas, bg=ARKA)
        self.canvas.create_window((0, 0), window=self.grid_frame, anchor="nw")
        self.grid_frame.bind("<Configure>",
                             lambda e: self.canvas.configure(scrollregion=self.canvas.bbox("all")))

        def tekerlek(e):
            self.canvas.yview_scroll(int(-e.delta / 120), "units")

        self.canvas.bind("<Enter>", lambda e: self.canvas.bind_all("<MouseWheel>", tekerlek))
        self.canvas.bind("<Leave>", lambda e: self.canvas.unbind_all("<MouseWheel>"))

        self.satirlar = []
        self.kur(self.yukle())

    def basliklar(self):
        for i in range(HAFTA):
            tk.Label(self.grid_frame, text=str(i + 1), width=4, bg=ARKA, fg=GRI,
                     font=("Segoe UI", 10, "bold")).grid(row=0, column=i + 1, padx=3, pady=(0, 2))

    def kur(self, veriler):
        for w in self.grid_frame.winfo_children():
            w.destroy()
        self.satirlar = []
        self.basliklar()
        for i, v in enumerate(veriler):
            self.satirlar.append(Satir(self, v, i + 1))
        if not self.satirlar or self.satirlar[-1].dolu_mu():
            self.yeni_bos_satir()

    def yeni_bos_satir(self):
        self.satirlar.append(Satir(self, bos_kayit(), len(self.satirlar) + 1))

    def satir_sil(self, satir):
        self.kur([s.veri for s in self.satirlar if s is not satir])
        self.kaydet()

    def yukle(self):
        try:
            with open(KAYIT, "r", encoding="utf-8") as f:
                d = json.load(f)
            temiz = []
            for x in d:
                if x.get("name", "").strip():
                    st = (x.get("st", []) + [0] * HAFTA)[:HAFTA]
                    temiz.append({"name": x["name"], "st": st})
            return temiz
        except Exception:
            return []

    def kaydet(self):
        try:
            veri = [s.veri for s in self.satirlar if s.dolu_mu()]
            with open(KAYIT, "w", encoding="utf-8") as f:
                json.dump(veri, f, ensure_ascii=False, indent=2)
        except Exception:
            pass


# ================================================================== YEMEK
def tr_lower(s):
    return s.replace("İ", "i").replace("I", "ı").lower()


class MetinCikar(HTMLParser):
    """HTML'i satır satır düz metne çevirir."""
    BLOK = {"p", "div", "br", "li", "ul", "ol", "tr", "td", "th", "table", "section",
            "article", "hr", "h1", "h2", "h3", "h4", "h5", "h6", "header", "footer"}

    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.satirlar = []
        self.tampon = []
        self.atla = 0

    def temizle(self):
        t = " ".join(" ".join(self.tampon).split())
        if t:
            self.satirlar.append(t)
        self.tampon = []

    def handle_starttag(self, tag, attrs):
        if tag in ("script", "style", "noscript", "title"):
            self.atla += 1
        if tag in self.BLOK:
            self.temizle()

    def handle_endtag(self, tag):
        if tag in ("script", "style", "noscript", "title") and self.atla:
            self.atla -= 1
        if tag in self.BLOK:
            self.temizle()

    def handle_data(self, data):
        if not self.atla:
            self.tampon.append(data)

    def close(self):
        super().close()
        self.temizle()


TARIH = re.compile(r"^(\d{1,2})\.(\d{1,2})\.(\d{4})")
TIPLER = {"öğrenci": "ogrenci", "vejetaryen": "vejetaryen", "personel": "personel"}
GUN_ADLARI = {tr_lower(g) for g in GUNLER}


def baslik_mi(t):
    tl = tr_lower(t)
    if len(t) < 60 and "yemek menüsü" in tl and not any(x in tl for x in ("bugün", "haftalık", "aylık")):
        for k, v in TIPLER.items():
            if k in tl:
                return ("tip", v)
    if len(t) < 30:
        if "öğle yemeği" in tl:
            return ("ogun", "ogle")
        if "akşam yemeği" in tl:
            return ("ogun", "aksam")
    return None


def bolum_sonu(t):
    tl = tr_lower(t)
    return bool(TARIH.match(t) or baslik_mi(t) or tl in TIPLER or tl.startswith("alerjen")
                or t.startswith("---"))


def ayristir(html):
    """Sayfadan {tip: {ogun: {'YYYY-AA-GG': 'menü metni'}}} üretir."""
    p = MetinCikar()
    p.feed(html)
    p.close()
    s = p.satirlar
    n = len(s)
    menu = {}
    tip = ogun = None
    i = 0
    while i < n:
        t = s[i]
        b = baslik_mi(t)
        if b:
            if b[0] == "tip":
                tip, ogun = b[1], None
            else:
                ogun = b[1]
            i += 1
            continue
        m = TARIH.match(t)
        if m and tip and ogun:
            try:
                tarih = datetime.date(int(m.group(3)), int(m.group(2)), int(m.group(1)))
            except ValueError:
                i += 1
                continue
            j = i + 1
            kalan = tr_lower(t[m.end():].strip())
            if not kalan and j < n and tr_lower(s[j]) in GUN_ADLARI:
                j += 1
            parcalar = []
            while j < n and not bolum_sonu(s[j]):
                parcalar.append(s[j])
                j += 1
            metin = "\n".join(parcalar).strip()
            if metin:
                menu.setdefault(tip, {}).setdefault(ogun, {}).setdefault(tarih.isoformat(), metin)
            i = j
            continue
        i += 1
    return menu


def sayfayi_indir(url=YEMEK_URL):
    istek = urllib.request.Request(url, headers={
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
                      "(KHTML, like Gecko) Chrome/120.0 Safari/537.36",
        "Accept-Language": "tr-TR,tr;q=0.9",
    })
    with urllib.request.urlopen(istek, timeout=20) as r:
        veri = r.read()
        cs = r.headers.get_content_charset() or "utf-8"
    return veri.decode(cs, errors="replace")


class YemekSekmesi:
    def __init__(self, parent):
        self.parent = parent
        parent.configure(bg=ARKA)
        self.menu = {}
        self.kuyruk = queue.Queue()
        self.tip = tk.StringVar(value="ogrenci")
        self.gorunum = tk.StringVar(value="bugun")

        ust = tk.Frame(parent, bg=ARKA)
        ust.pack(fill="x", padx=20, pady=(16, 6))
        for ad, val in (("Öğrenci", "ogrenci"), ("Vejetaryen", "vejetaryen"), ("Personel", "personel")):
            self.secenek(ust, ad, self.tip, val).pack(side="left", padx=2)
        tk.Frame(ust, width=24, bg=ARKA).pack(side="left")
        for ad, val in (("Bugün", "bugun"), ("Haftalık", "hafta")):
            self.secenek(ust, ad, self.gorunum, val).pack(side="left", padx=2)

        self.yenile_btn = tk.Button(ust, text="⟳ Yenile", command=self.yenile, padx=10, pady=4,
                                    cursor="hand2")
        self.yenile_btn.pack(side="right")
        self.durum = tk.Label(ust, text="", bg=ARKA, fg=GRI, font=("Segoe UI", 9))
        self.durum.pack(side="right", padx=10)

        self.icerik = tk.Frame(parent, bg=ARKA)
        self.icerik.pack(fill="both", expand=True, padx=20, pady=(6, 0))

        alt = tk.Frame(parent, bg=ARKA)
        alt.pack(fill="x", padx=20, pady=(4, 12))
        tk.Label(alt, text="Kaynak: uludag.edu.tr/yemek · Parantez içindeki sayılar alerjen kodlarıdır.",
                 bg=ARKA, fg=GRI, font=("Segoe UI", 9)).pack(side="left")
        tk.Button(alt, text="Alerjen listesi", bd=0, bg=ARKA, fg="#2a6fdb", cursor="hand2",
                  command=lambda: messagebox.showinfo("Alerjen listesi", "\n".join(ALERJENLER))
                  ).pack(side="right")

        self.onbellek_yukle()
        self.ciz()
        self.yenile()
        self.kontrol()

    def secenek(self, parent, ad, var, val):
        return tk.Radiobutton(parent, text=ad, variable=var, value=val, indicatoron=0,
                              padx=14, pady=5, bg=KART, selectcolor="#cfe8d6", relief="groove",
                              font=("Segoe UI", 10), command=self.ciz)

    # --- veri
    def onbellek_yukle(self):
        try:
            with open(ONBELLEK, "r", encoding="utf-8") as f:
                d = json.load(f)
            self.menu = d.get("menu", {})
            self.durum.config(text="Kayıtlı menü: " + d.get("zaman", ""))
        except Exception:
            self.menu = {}

    def onbellek_kaydet(self):
        try:
            with open(ONBELLEK, "w", encoding="utf-8") as f:
                json.dump({"zaman": datetime.datetime.now().strftime("%d.%m.%Y %H:%M"),
                           "menu": self.menu}, f, ensure_ascii=False)
        except Exception:
            pass

    def yenile(self):
        self.durum.config(text="Güncelleniyor…")
        self.yenile_btn.config(state="disabled")
        threading.Thread(target=self.indir, daemon=True).start()

    def indir(self):
        try:
            menu = ayristir(sayfayi_indir())
            if not menu:
                raise ValueError("sayfada menü bulunamadı")
            self.kuyruk.put((menu, None))
        except Exception as e:
            self.kuyruk.put((None, str(e)))

    def kontrol(self):
        try:
            while True:
                menu, hata = self.kuyruk.get_nowait()
                self.yenile_btn.config(state="normal")
                if menu:
                    self.menu = menu
                    self.onbellek_kaydet()
                    self.durum.config(text="Güncellendi: " + datetime.datetime.now().strftime("%H:%M"))
                else:
                    self.durum.config(text="Güncellenemedi (" + hata[:50] + ")")
                self.ciz()
        except queue.Empty:
            pass
        self.parent.after(200, self.kontrol)

    # --- çizim
    def temizle(self):
        for w in self.icerik.winfo_children():
            w.destroy()

    def ciz(self, *_):
        self.temizle()
        if not self.menu:
            tk.Label(self.icerik, text="Menü verisi yok.\nİnternet bağlantını kontrol edip “Yenile”ye bas.",
                     bg=ARKA, fg=GRI, font=("Segoe UI", 12)).pack(pady=40)
            return
        veri = self.menu.get(self.tip.get(), {})
        bugun = datetime.date.today()
        if self.gorunum.get() == "bugun":
            self.ciz_gunluk(veri, bugun)
        else:
            pazartesi = bugun - datetime.timedelta(days=bugun.weekday())
            if bugun.weekday() >= 5:
                pazartesi += datetime.timedelta(days=7)
            self.ciz_haftalik(veri, pazartesi, bugun)

    @staticmethod
    def ogun_metni(veri, ogun, gun):
        return veri.get(ogun, {}).get(gun.isoformat())

    def kart(self, parent, baslik, metin, vurgu=False):
        f = tk.Frame(parent, bg=KART, highlightbackground=CIZGI, highlightthickness=1)
        tk.Label(f, text=baslik, bg=KART, fg=GRI, font=("Segoe UI", 10, "bold"),
                 anchor="w").pack(fill="x", padx=14, pady=(10, 2))
        tk.Label(f, text=metin or "Menü bulunamadı", bg=KART, fg=METIN if metin else GRI,
                 font=("Segoe UI", 12), wraplength=420, justify="left", anchor="nw"
                 ).pack(fill="both", expand=True, padx=14, pady=(0, 12))
        return f

    def ciz_gunluk(self, veri, gun):
        baslik = f"{gun.day} {AYLAR[gun.month - 1]} {gun.year} · {GUNLER[gun.weekday()]}"
        tk.Label(self.icerik, text=baslik, bg=ARKA, fg=METIN,
                 font=("Segoe UI", 14, "bold")).pack(anchor="w", pady=(4, 8))
        ogle = self.ogun_metni(veri, "ogle", gun)
        aksam = self.ogun_metni(veri, "aksam", gun)
        if not ogle and not aksam:
            tk.Label(self.icerik, text="Bugün için menü bulunamadı (hafta sonu veya tatil olabilir).\n"
                                       "“Haftalık” sekmesinden yaklaşan günlere bakabilirsin.",
                     bg=ARKA, fg=GRI, font=("Segoe UI", 11), justify="left").pack(anchor="w", pady=10)
            return
        satir = tk.Frame(self.icerik, bg=ARKA)
        satir.pack(fill="x")
        satir.columnconfigure((0, 1), weight=1, uniform="k")
        self.kart(satir, "ÖĞLE YEMEĞİ", ogle).grid(row=0, column=0, sticky="nsew", padx=(0, 8))
        self.kart(satir, "AKŞAM YEMEĞİ", aksam).grid(row=0, column=1, sticky="nsew", padx=(8, 0))

    def ciz_haftalik(self, veri, pazartesi, bugun):
        son = pazartesi + datetime.timedelta(days=4)
        tk.Label(self.icerik, text=f"{pazartesi.day} {AYLAR[pazartesi.month - 1]} – "
                                   f"{son.day} {AYLAR[son.month - 1]} {son.year}",
                 bg=ARKA, fg=METIN, font=("Segoe UI", 14, "bold")).pack(anchor="w", pady=(4, 8))
        g = tk.Frame(self.icerik, bg=ARKA)
        g.pack(fill="both", expand=True)
        g.columnconfigure(1, weight=1, uniform="k")
        g.columnconfigure(2, weight=1, uniform="k")
        for c, ad in ((1, "ÖĞLE"), (2, "AKŞAM")):
            tk.Label(g, text=ad, bg=ARKA, fg=GRI, font=("Segoe UI", 9, "bold")
                     ).grid(row=0, column=c, sticky="w", padx=6)
        for r in range(5):
            gun = pazartesi + datetime.timedelta(days=r)
            bugunku = gun == bugun
            tk.Label(g, text=f"{GUNLER[r]}\n{gun.day} {AYLAR[gun.month - 1][:3]}",
                     bg=RENK_YESIL if bugunku else ARKA, fg="white" if bugunku else METIN,
                     font=("Segoe UI", 10, "bold"), width=11, justify="left", anchor="w",
                     padx=6).grid(row=r + 1, column=0, sticky="nsew", pady=3)
            for c, ogun in ((1, "ogle"), (2, "aksam")):
                metin = self.ogun_metni(veri, ogun, gun)
                tk.Label(g, text=metin or "—", bg=KART, fg=METIN if metin else GRI,
                         font=("Segoe UI", 10), wraplength=400, justify="left", anchor="nw",
                         padx=10, pady=8, highlightbackground=CIZGI, highlightthickness=1
                         ).grid(row=r + 1, column=c, sticky="nsew", padx=4, pady=3)
            g.rowconfigure(r + 1, weight=1)


# ============================================================= DUYURULAR
AYLAR_KUCUK = {tr_lower(a): i + 1 for i, a in enumerate(AYLAR)}
DOSYA_UZANTI = re.compile(r"\.(pdf|docx?|xlsx?|pptx?|zip|rar|7z)(\?.*)?$", re.I)
MAX_DUYURU = 15


class BaglantiCikar(HTMLParser):
    """Başlıkları ve bağlantıları sırayla toplar."""

    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.ogeler = []
        self.hbuf = self.abuf = None
        self.ahref = None

    @staticmethod
    def temiz(parcalar):
        return " ".join(" ".join(parcalar).split())

    def handle_starttag(self, tag, attrs):
        if tag in ("h1", "h2", "h3", "h4", "h5", "h6"):
            self.hbuf = []
        elif tag == "a":
            self.ahref = dict(attrs).get("href")
            self.abuf = []

    def handle_data(self, data):
        for b in (self.hbuf, self.abuf):
            if b is not None:
                b.append(data)

    def handle_endtag(self, tag):
        if tag in ("h1", "h2", "h3", "h4", "h5", "h6") and self.hbuf is not None:
            self.ogeler.append(("h", self.temiz(self.hbuf)))
            self.hbuf = None
        elif tag == "a" and self.abuf is not None:
            if self.ahref:
                self.ogeler.append(("a", self.ahref, self.temiz(self.abuf)))
            self.abuf = self.ahref = None


def baglantilar(html):
    p = BaglantiCikar()
    p.feed(html)
    p.close()
    return p.ogeler


def duyuru_ana_sayfa_ayristir(html, taban):
    """Fakülte ana sayfasındaki 'GENEL DUYURULAR' bölümünü (başlık, link) olarak okur."""
    sonuc = []
    icinde = False
    for o in baglantilar(html):
        if o[0] == "h":
            icinde = "genel duyurular" in tr_lower(o[1])
        elif icinde and o[0] == "a":
            href, baslik = o[1], o[2]
            if not baslik or href.startswith("#") or "tüm duyurular" in tr_lower(baslik):
                continue
            sonuc.append((baslik, urljoin(taban, href)))
    return sonuc


def tarih_bul(metin):
    """Metindeki ilk geçerli tarihi 'YYYY-AA-GG' olarak döner."""
    t = tr_lower(metin)
    adaylar = []
    for m in re.finditer(r"(\d{1,2})[./](\d{1,2})[./](\d{4})", t):
        adaylar.append((m.start(), int(m.group(3)), int(m.group(2)), int(m.group(1))))
    for m in re.finditer(r"(\d{1,2})\s+(" + "|".join(AYLAR_KUCUK) + r")\s+(\d{4})", t):
        adaylar.append((m.start(), int(m.group(3)), AYLAR_KUCUK[m.group(2)], int(m.group(1))))
    for m in re.finditer(r"(\d{4})-(\d{2})-(\d{2})", t):
        adaylar.append((m.start(), int(m.group(1)), int(m.group(2)), int(m.group(3))))
    for _, y, mo, g in sorted(adaylar):
        try:
            return datetime.date(y, mo, g).isoformat()
        except ValueError:
            continue
    return ""


def url_id(url):
    m = re.search(r"-(\d+)/?$", url.split("?")[0])
    return int(m.group(1)) if m else 0


def detay_ayristir(html, baslik):
    """Duyuru sayfasından (metin, tarih) çıkarır."""
    p = MetinCikar()
    p.feed(html)
    p.close()
    s = p.satirlar
    bt = tr_lower(baslik)
    start = None
    for i, l in enumerate(s):
        if tr_lower(l) == bt:
            start = i
            break
    if start is None:
        for i, l in enumerate(s):
            if bt in tr_lower(l) and len(l) < len(baslik) + 40:
                start = i
                break
    if start is None:
        start = -1
        for i, l in enumerate(s):
            if len(l) > 100:
                start = i - 1
                break
    son = len(s)
    for i in range(start + 1, len(s)):
        tl = tr_lower(s[i])
        if tl.startswith("site içi arama") or tl.startswith("hızlı bağlantılar") or tl.startswith("iletişim:"):
            son = i
            break
    govde = [l for l in s[start + 1:son] if tr_lower(l) != bt]

    tarih = ""
    t = re.search(r'<time[^>]*datetime="([^"]+)"', html)
    if t:
        tarih = tarih_bul(t.group(1))
    if not tarih:
        for l in s[max(0, start - 3):start + 4]:
            if len(l) < 40:
                tarih = tarih_bul(l)
                if tarih:
                    break
    if tarih and govde and len(govde[0]) < 40 and tarih_bul(govde[0]) == tarih:
        govde = govde[1:]
    return "\n\n".join(govde)[:8000], tarih


def detay_cek(oge, nav):
    baslik, url = oge
    d = {"b": baslik, "u": url, "t": "", "i": "", "e": [], "id": url_id(url)}
    try:
        html = sayfayi_indir(url)
        d["i"], d["t"] = detay_ayristir(html, baslik)
        gorulen = set()
        for o in baglantilar(html):
            if o[0] != "a" or o[1].startswith("#"):
                continue
            u = urljoin(url, o[1])
            if DOSYA_UZANTI.search(u) and u not in nav and u not in gorulen:
                gorulen.add(u)
                ad = o[2] or u.rsplit("/", 1)[-1]
                d["e"].append([ad, u])
    except Exception as e:
        d["i"] = f"(İçerik alınamadı: {e})"
    return d


def duyurulari_cek():
    ana_html = sayfayi_indir(ANA_URL)
    liste = duyuru_ana_sayfa_ayristir(ana_html, ANA_URL)[:MAX_DUYURU]
    if not liste:
        raise ValueError("duyuru bulunamadı")
    nav = {urljoin(ANA_URL, o[1]) for o in baglantilar(ana_html) if o[0] == "a"}
    with ThreadPoolExecutor(max_workers=6) as ex:
        sonuc = list(ex.map(lambda x: detay_cek(x, nav), liste))
    sonuc.sort(key=lambda d: (d["t"], d["id"]), reverse=True)
    return sonuc


def tarih_goster(iso):
    try:
        return datetime.date.fromisoformat(iso).strftime("%d.%m.%Y")
    except Exception:
        return ""


class DuyuruSekmesi:
    def __init__(self, parent):
        self.parent = parent
        parent.configure(bg=ARKA)
        self.liste = []
        self.kuyruk = queue.Queue()
        self.arama = tk.StringVar()
        self.secili = None

        ust = tk.Frame(parent, bg=ARKA)
        ust.pack(fill="x", padx=20, pady=(16, 6))
        tk.Label(ust, text="Duyurular · İİBF", font=("Segoe UI", 15, "bold"), bg=ARKA,
                 fg=METIN).pack(side="left")
        self.yenile_btn = tk.Button(ust, text="⟳ Yenile", command=self.yenile, padx=10, pady=4,
                                    cursor="hand2")
        self.yenile_btn.pack(side="right")
        self.durum = tk.Label(ust, text="", bg=ARKA, fg=GRI, font=("Segoe UI", 9))
        self.durum.pack(side="right", padx=10)

        govde = tk.Frame(parent, bg=ARKA)
        govde.pack(fill="both", expand=True, padx=20, pady=(0, 12))
        govde.columnconfigure(0, weight=2, uniform="c")
        govde.columnconfigure(1, weight=3, uniform="c")
        govde.rowconfigure(1, weight=1)

        # sol: arama + liste
        tk.Entry(govde, textvariable=self.arama, font=("Segoe UI", 10), relief="solid", bd=1
                 ).grid(row=0, column=0, sticky="ew", padx=(0, 10), pady=(0, 6), ipady=3)
        self.arama.trace_add("write", lambda *_: self.ciz())
        sol = tk.Frame(govde, bg=ARKA)
        sol.grid(row=1, column=0, sticky="nsew", padx=(0, 10))
        self.agac = ttk.Treeview(sol, columns=("baslik", "tarih"), show="headings",
                                 selectmode="browse")
        self.agac.heading("baslik", text="Başlık", anchor="w")
        self.agac.heading("tarih", text="Tarih", anchor="w")
        self.agac.column("baslik", width=300, anchor="w")
        self.agac.column("tarih", width=90, anchor="w", stretch=False)
        sb = ttk.Scrollbar(sol, orient="vertical", command=self.agac.yview)
        self.agac.configure(yscrollcommand=sb.set)
        sb.pack(side="right", fill="y")
        self.agac.pack(side="left", fill="both", expand=True)
        self.agac.bind("<<TreeviewSelect>>", self.sec)

        # sağ: içerik
        sag = tk.Frame(govde, bg=KART, highlightbackground=CIZGI, highlightthickness=1)
        sag.grid(row=0, column=1, rowspan=2, sticky="nsew")
        self.baslik_lbl = tk.Label(sag, text="Bir duyuru seç", bg=KART, fg=METIN, anchor="w",
                                   justify="left", font=("Segoe UI", 13, "bold"), wraplength=520)
        self.baslik_lbl.pack(fill="x", padx=14, pady=(12, 0))
        self.tarih_lbl = tk.Label(sag, text="", bg=KART, fg=GRI, anchor="w", font=("Segoe UI", 9))
        self.tarih_lbl.pack(fill="x", padx=14)
        alt = tk.Frame(sag, bg=KART)
        alt.pack(side="bottom", fill="x", padx=14, pady=(4, 10))
        self.ekler = tk.Frame(alt, bg=KART)
        self.ekler.pack(fill="x")
        self.ac_btn = tk.Button(alt, text="Tarayıcıda aç ↗", bd=0, bg=KART, fg="#2a6fdb",
                                cursor="hand2", command=self.tarayicida_ac)
        self.ac_btn.pack(anchor="w", pady=(4, 0))
        metin_kap = tk.Frame(sag, bg=KART)
        metin_kap.pack(fill="both", expand=True, padx=14, pady=8)
        self.metin = tk.Text(metin_kap, wrap="word", font=("Segoe UI", 10), bg=KART, fg=METIN,
                             relief="flat", state="disabled", padx=0, pady=0)
        tsb = ttk.Scrollbar(metin_kap, orient="vertical", command=self.metin.yview)
        self.metin.configure(yscrollcommand=tsb.set)
        tsb.pack(side="right", fill="y")
        self.metin.pack(side="left", fill="both", expand=True)

        self.onbellek_yukle()
        self.ciz()
        self.yenile()
        self.kontrol()

    # --- veri
    def onbellek_yukle(self):
        try:
            with open(DUYURU_ONBELLEK, "r", encoding="utf-8") as f:
                d = json.load(f)
            self.liste = d.get("liste", [])
            self.durum.config(text="Kayıtlı liste: " + d.get("zaman", ""))
        except Exception:
            self.liste = []

    def onbellek_kaydet(self):
        try:
            with open(DUYURU_ONBELLEK, "w", encoding="utf-8") as f:
                json.dump({"zaman": datetime.datetime.now().strftime("%d.%m.%Y %H:%M"),
                           "liste": self.liste}, f, ensure_ascii=False)
        except Exception:
            pass

    def yenile(self):
        self.durum.config(text="Güncelleniyor…")
        self.yenile_btn.config(state="disabled")
        threading.Thread(target=self.indir, daemon=True).start()

    def indir(self):
        try:
            self.kuyruk.put((duyurulari_cek(), None))
        except Exception as e:
            self.kuyruk.put((None, str(e)))

    def kontrol(self):
        try:
            while True:
                liste, hata = self.kuyruk.get_nowait()
                self.yenile_btn.config(state="normal")
                if liste:
                    self.liste = liste
                    self.onbellek_kaydet()
                    self.durum.config(text="Güncellendi: " + datetime.datetime.now().strftime("%H:%M"))
                else:
                    self.durum.config(text="Güncellenemedi (" + hata[:50] + ")")
                self.ciz()
        except queue.Empty:
            pass
        self.parent.after(200, self.kontrol)

    # --- gösterim
    def ciz(self):
        onceki = self.secili["u"] if self.secili else None
        self.agac.delete(*self.agac.get_children())
        aranan = tr_lower(self.arama.get().strip())
        yeniden = None
        for i, d in enumerate(self.liste):
            if aranan and aranan not in tr_lower(d["b"]) and aranan not in tr_lower(d.get("i", "")):
                continue
            iid = f"d{i}"
            self.agac.insert("", "end", iid=iid, values=(d["b"], tarih_goster(d["t"])))
            if d["u"] == onceki:
                yeniden = iid
        if yeniden:
            self.agac.selection_set(yeniden)

    def sec(self, _=None):
        sec = self.agac.selection()
        if not sec:
            return
        d = self.liste[int(sec[0][1:])]
        self.secili = d
        self.baslik_lbl.config(text=d["b"])
        self.tarih_lbl.config(text=("Tarih: " + tarih_goster(d["t"])) if d["t"] else "")
        self.metin.config(state="normal")
        self.metin.delete("1.0", "end")
        self.metin.insert("1.0", d.get("i") or "(Duyuru metni yok. Ekleri veya tarayıcıyı kullan.)")
        self.metin.config(state="disabled")
        for w in self.ekler.winfo_children():
            w.destroy()
        for ad, url in d.get("e", []):
            tk.Button(self.ekler, text="📎 " + ad[:70], bd=0, bg=KART, fg="#2a6fdb", cursor="hand2",
                      anchor="w", command=lambda u=url: webbrowser.open(u)).pack(anchor="w")

    def tarayicida_ac(self):
        if self.secili:
            webbrowser.open(self.secili["u"])


# ================================================================== ANA
def main():
    root = tk.Tk()
    root.title("Okul Asistanı")
    root.geometry("1120x660")
    root.configure(bg=ARKA)

    stil = ttk.Style()
    stil.configure("TNotebook.Tab", font=("Segoe UI", 11), padding=(18, 7))
    stil.configure("Treeview", rowheight=32, font=("Segoe UI", 10))
    stil.configure("Treeview.Heading", font=("Segoe UI", 10, "bold"))

    nb = ttk.Notebook(root)
    nb.pack(fill="both", expand=True)
    f1 = tk.Frame(nb, bg=ARKA)
    f2 = tk.Frame(nb, bg=ARKA)
    nb.add(f1, text="Devamsızlık")
    nb.add(f2, text="Yemek")
    f3 = tk.Frame(nb, bg=ARKA)
    nb.add(f3, text="Duyurular")

    DevamsizlikSekmesi(f1)
    YemekSekmesi(f2)
    DuyuruSekmesi(f3)
    root.mainloop()


if __name__ == "__main__":
    main()
