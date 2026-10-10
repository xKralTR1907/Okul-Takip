"""Yemek menüsünü ve duyuruları siteden çekip data.json dosyasına yazar.
GitHub Actions tarafından düzenli aralıklarla çalıştırılır; bilgisayarında da
`python veri_guncelle.py` ile elle çalıştırabilirsin.
devamsizlik_takip.py ile aynı klasörde olmalıdır (ayrıştırma kodunu oradan kullanır)."""
import datetime
import json
import os
import sys
import types

# Sunucuda ekran/Tkinter yok; masaüstü uygulamasındaki ayrıştırıcıları kullanmak için
# Tkinter modüllerini boş taklitlerle değiştiriyoruz.
for _m in ("tkinter", "tkinter.ttk", "tkinter.messagebox"):
    sys.modules[_m] = types.ModuleType(_m)
sys.modules["tkinter"].ttk = sys.modules["tkinter.ttk"]
sys.modules["tkinter"].messagebox = sys.modules["tkinter.messagebox"]

KLASOR = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, KLASOR)
import devamsizlik_takip as d  # noqa: E402

CIKTI = os.path.join(KLASOR, "data.json")


def main():
    try:
        with open(CIKTI, "r", encoding="utf-8") as f:
            eski = json.load(f)
    except Exception:
        eski = {}
    yemek = eski.get("yemek", {})
    duyurular = eski.get("duyurular", [])
    basarili = 0

    try:
        m = d.ayristir(d.sayfayi_indir(d.YEMEK_URL))
        if not m:
            raise ValueError("menü bulunamadı")
        yemek = m
        basarili += 1
        print("Yemek menüsü güncellendi.")
    except Exception as e:
        print("Yemek menüsü alınamadı:", e)

    try:
        liste = d.duyurulari_cek()
        duyurular = liste
        basarili += 1
        print(f"{len(liste)} duyuru güncellendi.")
    except Exception as e:
        print("Duyurular alınamadı:", e)

    if not basarili:
        sys.exit("Hiçbir veri alınamadı.")

    veri = {
        "guncelleme": datetime.datetime.now(datetime.timezone.utc).isoformat(timespec="seconds"),
        "yemek": yemek,
        "duyurular": duyurular,
    }
    with open(CIKTI, "w", encoding="utf-8") as f:
        json.dump(veri, f, ensure_ascii=False, indent=1)


if __name__ == "__main__":
    main()
