import streamlit as st
import pandas as pd
import pdfplumber
import re
import tempfile
import os
import plotly.express as px

st.set_page_config(page_title="Dashboard Pengeluaran", layout="wide")
st.title("📊 Dashboard Pengeluaran")

# ================= Helper Parsing =================
num_regex = r"(\d{1,3}(?:[.,]\d{3})*(?:[.,]\d{2})?)"
tanggal_re = re.compile(r"^\s*(\d{1,2}/\d{1,2})")

def clean_number(num_str):
    if num_str is None:
        return None
    num_str = num_str.strip()
    if "," in num_str and num_str.rfind(",") > num_str.rfind("."):
        num_str = num_str.replace(".", "").replace(",", ".")
    else:
        num_str = num_str.replace(",", "")
    try:
        return float(num_str)
    except:
        return None

def is_name_candidate(line):
    if not line:
        return False
    if re.search(r"\d", line):
        return False
    if re.fullmatch(r"[A-Z\s\.\&\-]+", line):
        letters = re.sub(r"[^A-Z]", "", line)
        return len(letters) > 5
    return False

def candidate_number_valid(s, whole_line):
    if re.match(r"^\d+\s*/\s*\d+$", whole_line.strip()):
        return False
    digits_only = re.sub(r"\D", "", s)
    if '.' in s or ',' in s:
        return True
    if len(digits_only) >= 4:
        return True
    return False

def join_name_lines(lines, start_idx, skip_keywords):
    full_name = lines[start_idx].strip()
    for offset in range(1, 5):
        if start_idx + offset < len(lines):
            next_line = lines[start_idx + offset].strip()
            if next_line.isupper() and not re.search(r"\d", next_line):
                if not any(word in next_line for word in skip_keywords):
                    full_name += " " + next_line
                else:
                    break
            else:
                break
    return full_name.strip()

def extract_account_owner(first_page_lines):
    skip_keywords = [
        "REKENING", "KCP", "CABANG", "BANK", "BCA", "INDONESIA",
        "HALAMAN", "PERIODE", "MATA UANG", "NO. REKENING",
        "TANGGAL", "KETERANGAN", "MUTASI", "SALDO", "CBG"
    ]
    for line in first_page_lines:
        m = re.search(r"(NAMA|PEMILIK)\s+REKENING\s*:\s*(.+)", line, re.I)
        if m:
            return m.group(2).strip()
    for idx, line in enumerate(first_page_lines):
        if "REKENING TAHAPAN" in line.upper():
            for offset in range(1, 5):
                if idx + offset < len(first_page_lines):
                    candidate = first_page_lines[idx + offset].strip()
                    if candidate.isupper() and not re.search(r"\d", candidate):
                        if not any(word in candidate for word in skip_keywords):
                            return join_name_lines(first_page_lines, idx + offset, skip_keywords)
    for idx, line in enumerate(first_page_lines):
        if line.isupper() and not re.search(r"\d", line) and len(line.split()) >= 2:
            if not any(word in line for word in skip_keywords):
                return join_name_lines(first_page_lines, idx, skip_keywords)
    if len(first_page_lines) > 1:
        return first_page_lines[1].strip()
    return None

def categorize_transaction(keterangan):
    keterangan_upper = keterangan.upper()
    if "TRSF" in keterangan_upper:
        return "Transfer"
    elif "TTS BY TPKD" in keterangan_upper or "TTS BY TKPD" in keterangan_upper:
        return "TikTok Shop"
    elif "GOOGLE VIDIO" in keterangan_upper or "VIDIO.COM" in keterangan_upper:
        return "Vidio"
    elif "GOPAY" in keterangan_upper or "GOJEK" in keterangan_upper:
        return "Gojek"
    elif "GRAB" in keterangan_upper:
        return "Grab"
    elif "SHOPEE.CO.ID" in keterangan_upper or "SHOPEE" in keterangan_upper:
        return "Shopee"
    elif "FLAZZ" in keterangan_upper:
        return "Flazz"
    elif "TARIKAN ATM" in keterangan_upper:
        return "Tarik Tunai"
    elif "BIAYA ADM" in keterangan_upper:
        return "Biaya Admin"
    else:
        return "Lainnya"

def parse_bca_pdf(file_path):
    rows = []
    skip_keywords = ["SALDO AWAL", "MUTASI DB", "MUTASI CR", "SALDO AKHIR"]

    with pdfplumber.open(file_path) as pdf:
        first_page_lines = [l.strip() for l in (pdf.pages[0].extract_text() or "").split("\n") if l.strip()]
        pemilik_rekening = extract_account_owner(first_page_lines)

        for page in pdf.pages:
            lines = [l.strip() for l in (page.extract_text() or "").split("\n") if l.strip()]
            n = len(lines)
            i = 0
            while i < n:
                line = lines[i]
                if any(k in line.upper() for k in skip_keywords):
                    i += 1
                    continue
                mdate = tanggal_re.match(line)
                if mdate:
                    tanggal = mdate.group(1)
                    keterangan = line[mdate.end():].strip()
                    nama = "-"
                    mutasi = None
                    tipe = None
                    for j in range(i, min(i + 3, n)):
                        if tanggal_re.match(lines[j]) and j != i:
                            break
                        tipe_match = re.search(r"\b(DB|CR|KR)\b", lines[j], re.I)
                        if tipe_match:
                            tipe = tipe_match.group(1).upper()
                            nums = re.findall(num_regex, lines[j])
                            for s in nums:
                                if candidate_number_valid(s, lines[j]):
                                    mutasi = clean_number(s)
                                    break
                            if mutasi is not None:
                                break
                    if mutasi is not None:
                        start_idx = j + 1
                        for k in range(start_idx, min(start_idx + 5, n)):
                            if tanggal_re.match(lines[k]):
                                break
                            if is_name_candidate(lines[k]):
                                nama = lines[k]
                                break
                    rows.append({
                        "Tanggal": tanggal,
                        "Keterangan": keterangan,
                        "Nama": nama,
                        "Mutasi": mutasi,
                        "Tipe": tipe
                    })
                i += 1

    df = pd.DataFrame(rows, columns=["Tanggal", "Keterangan", "Nama", "Mutasi", "Tipe"])
    df["Kategori"] = df["Keterangan"].apply(categorize_transaction)

    mask_gajian = (
        df["Nama"].str.upper() == "HERYANTO"
    ) & (df["Mutasi"] > 500_000) & (df["Tipe"].isin(["CR", "KR"]))
    df.loc[mask_gajian, "Kategori"] = "Gajian Pertama"

    return df, pemilik_rekening

# ================= Fungsi Pie Chart =================
def buat_pie_chart(data, value_col, title, is_rupiah=False):
    fig = px.pie(
        data,
        names="Kategori",
        values=value_col,
        title=title,
        hole=0.5,
        color="Kategori",
        color_discrete_map=color_map
    )
    fig.update_traces(
        textinfo="percent+label",
        textfont=dict(color="#FFFFFF", size=14),
        pull=[0.05]*len(data),
        marker=dict(line=dict(color="#FFFFFF", width=2)),
        hovertemplate=(
            "<b>%{label}</b><br>%{percent}<br>Rp %{value:,.0f}<extra></extra>"
            if is_rupiah
            else "<b>%{label}</b><br>%{percent}<br>Jumlah: %{value} transaksi<extra></extra>"
        )
    )
    fig.update_layout(
        title_font=dict(size=20, color="#FFFFFF"),
        legend_title_text="Kategori",
        legend=dict(font=dict(size=15, color="#FFFFFF")),
        paper_bgcolor="#222222",
        plot_bgcolor="#222222",
        margin=dict(t=80, b=100, l=80, r=80)
    )
    return fig

# ================= Streamlit App =================
uploaded_file = st.file_uploader("Upload file mutasi rekening (PDF)", type=["pdf"])

if uploaded_file:
    with tempfile.NamedTemporaryFile(delete=False, suffix=".pdf") as tmp:
        tmp.write(uploaded_file.read())
        temp_pdf_path = tmp.name

    try:
        df, pemilik = parse_bca_pdf(temp_pdf_path)

        if pemilik:
            st.markdown(f"### 🏦 Pemilik Rekening: **{pemilik}**")
        else:
            st.warning("⚠️ Nama pemilik rekening tidak ditemukan.")

        if df.empty:
            st.error("Tidak ada transaksi yang terbaca dari PDF.")
        else:
            st.subheader("📄 Hasil Konversi PDF → Tabel CSV")
            st.dataframe(df)

            csv_data = df.to_csv(index=False).encode("utf-8")
            st.download_button(
                label="⬇️ Download Semua Transaksi (CSV)",
                data=csv_data,
                file_name="mutasi_bca.csv",
                mime="text/csv"
            )

            # Hitung total masuk/keluar
            if pemilik:
                pemilik_upper = pemilik.upper()
                total_debit = df.loc[
                    (df["Tipe"] == "DB") & (df["Nama"].str.upper() != pemilik_upper),
                    "Mutasi"
                ].sum()
            else:
                total_debit = df.loc[df["Tipe"] == "DB", "Mutasi"].sum()

            total_kredit = df.loc[df["Tipe"].isin(["CR", "KR"]), "Mutasi"].sum()

            st.markdown(f"### 🔢 Total Duit Keluar: Rp {total_debit:,.0f}")
            st.markdown(f"### 🔢 Total Duit Masuk: Rp {total_kredit:,.0f}")
            st.markdown(f"### 🔢 Total Pengeluaran: Rp {total_kredit-total_debit:,.0f}")
            st.markdown("<br><br><br>", unsafe_allow_html=True)

            # Warna kategori
            warna_kategori = px.colors.qualitative.Plotly
            kategori_unik = df["Kategori"].unique()
            color_map = {kategori: warna_kategori[i % len(warna_kategori)] for i, kategori in enumerate(kategori_unik)}

            # ==== Pie Chart 1: Jumlah transaksi (hanya DB, termasuk Gajian Pertama) ====
            if pemilik:
                df_pie1 = df[(df["Tipe"] == "DB") & (df["Nama"].str.upper() != pemilik_upper)]
            else:
                df_pie1 = df[df["Tipe"] == "DB"]

            max_total_pengeluaran = total_kredit - total_debit
            total_di_pie1 = df_pie1["Mutasi"].sum()
            if total_di_pie1 > max_total_pengeluaran and total_di_pie1 != 0:
                df_pie1 = df_pie1.copy()
                df_pie1["Mutasi"] *= (max_total_pengeluaran / total_di_pie1)

            kategori_counts = df_pie1["Kategori"].value_counts().reset_index()
            kategori_counts.columns = ["Kategori", "Jumlah Transaksi"]

            st.plotly_chart(
                buat_pie_chart(kategori_counts, "Jumlah Transaksi", "Distribusi Jumlah Transaksi per Kategori", is_rupiah=False),
                use_container_width=True
            )

            # ==== Pie Chart 2: Total pengeluaran ====
            if pemilik:
                df_pengeluaran = df[(df["Tipe"] == "DB") & (df["Nama"].str.upper() != pemilik_upper)]
            else:
                df_pengeluaran = df[df["Tipe"] == "DB"]

            total_di_pie2 = df_pengeluaran["Mutasi"].sum()
            if total_di_pie2 > max_total_pengeluaran and total_di_pie2 != 0:
                df_pengeluaran["Mutasi"] *= (max_total_pengeluaran / total_di_pie2)

            kategori_sums = df_pengeluaran.groupby("Kategori")["Mutasi"].sum().reset_index()
            st.plotly_chart(
                buat_pie_chart(kategori_sums, "Mutasi", "Distribusi Total Pengeluaran per Kategori", is_rupiah=True),
                use_container_width=True
            )

    except Exception as e:
        st.error(f"Gagal membaca PDF: {e}")

    os.remove(temp_pdf_path)
else:
    st.info("Silakan upload file PDF mutasi rekening dari myBCA.")
