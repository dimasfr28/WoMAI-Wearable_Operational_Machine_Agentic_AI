from pydantic import BaseModel


class ChatIn(BaseModel):
    message: str
    session_id: str
    # Mesin aktif (rancangan.txt Section 8: "Hilangkan pilih mesin dan
    # inputasi input manual variabel di fitur chat/copilot") — frontend
    # mengirim ini dari state mesin aktif global (dipilih sebelum masuk chat),
    # BUKAN diminta lagi di dalam obrolan. Kalau None (mis. klien lama/API
    # eksternal), intent classifier tetap fallback ke ekstraksi nama mesin
    # dari teks pesan seperti sebelumnya.
    machine_id: str | None = None
