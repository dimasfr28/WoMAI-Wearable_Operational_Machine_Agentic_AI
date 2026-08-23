"""One-time seed script: populate `sops` table dengan SOP tambahan yang
selaras dengan mekanisme kegagalan fisik model klasifikasi (lihat
app/ml/predictor_clasification.py: 4 fitur mentah + 5 fitur turunan fisik
Temp_diff, Temp_ratio, Wear_x_rpm, Cooling_margin_rate, Thermal_wear_load).

Hanya berisi "Penanganan Beban Termal-Wear Tinggi pada RPM Rendah" -- SOP
untuk tool wear tinggi dan overheating/suhu proses tinggi SUDAH ADA di
tabel `sops` ("Penggantian Tool Akibat Keausan Tinggi" dan "Penanganan
Overheating pada Proses (Suhu Proses Tinggi)"), jadi tidak diduplikasi
di sini.

Dipakai oleh intent `sop_lookup`/`predict`/`latest_report` di
app/api/routes_chat.py lewat match_sop().

Run manually: `docker compose exec backend python scripts/seed_sops.py`
Safe to re-run: skip SOP yang title-nya sudah ada di tabel `sops`.
"""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app.db.models import Sop  # noqa: E402
from app.db.session import SessionLocal  # noqa: E402

SOPS = [
    {
        "title": "Penanganan Beban Termal-Wear Tinggi pada RPM Rendah",
        "symptoms": (
            "Kombinasi tool wear tinggi bersamaan dengan RPM rendah dan selisih suhu besar "
            "(Thermal_wear_load dan Wear_x_rpm tinggi), mesin terasa lebih berat saat memotong, "
            "prediksi model konsisten menunjukkan risiko gagal tinggi walau tiap parameter sensor "
            "individual belum ekstrem."
        ),
        "body": (
            "Thermal_wear_load (Temp_diff x tool_wear_min) dan Wear_x_rpm (tool_wear_min x RPM) "
            "adalah fitur interaksi yang menangkap kombinasi beban termal dan mekanis sekaligus. "
            "Nilai tinggi pada fitur-fitur ini menandakan tool yang sudah aus dipaksa bekerja pada "
            "kombinasi suhu dan kecepatan yang tidak sesuai, mempercepat kegagalan meski masing-masing "
            "sensor individual belum melewati ambang ekstrem."
        ),
        "steps": [
            {
                "id": "s1",
                "text": "Hentikan proses dan lakukan pemeriksaan gabungan: kondisi tool, suhu proses, dan RPM aktual dibandingkan parameter rekomendasi.",
                "priority": "segera",
                "estimated_minutes": 15,
            },
            {
                "id": "s2",
                "text": "Ganti tool yang sudah aus terlebih dahulu, karena tool wear adalah komponen paling mudah dikoreksi pada kombinasi ini.",
                "priority": "segera",
                "estimated_minutes": 20,
            },
            {
                "id": "s3",
                "text": "Sesuaikan RPM ke rentang yang direkomendasikan untuk material dan tool baru sebelum melanjutkan produksi.",
                "priority": "segera",
                "estimated_minutes": 10,
            },
            {
                "id": "s4",
                "text": "Tinjau ulang parameter proses (feed rate, RPM, jadwal ganti tool) untuk kombinasi material/tool ini agar kombinasi beban serupa tidak terulang.",
                "priority": "terjadwal",
                "estimated_minutes": 20,
            },
        ],
        "reference": "Haas CNC Maintenance Guide - Combined Thermal & Mechanical Load",
    },
]


def main():
    db = SessionLocal()
    try:
        existing_titles = {s.title for s in db.query(Sop).all()}
        for sop_data in SOPS:
            if sop_data["title"] in existing_titles:
                print(f"  [skip] {sop_data['title']}: already exists")
                continue
            sop = Sop(
                title=sop_data["title"],
                symptoms=sop_data["symptoms"],
                body=sop_data["body"],
                steps=sop_data["steps"],
                reference=sop_data["reference"],
            )
            db.add(sop)
            db.commit()
            print(f"  [ok] {sop_data['title']}: seeded")
    finally:
        db.close()


if __name__ == "__main__":
    main()
