
import streamlit as st
from PyPDF2 import PdfReader
import re
import textstat
from PIL import Image
import fitz
import os

st.set_page_config(page_title="NikLabs: Dudley DocLiberator (Ultra Beta)", layout="centered")

# --- Header Branding ---
col1, col2 = st.columns([1, 5])
with col1:
    logo = Image.open("dudley-logo.jpg")
    st.image(logo, width=100)
with col2:
    st.title("NikLabs: Dudley DocLiberator (Ultra Beta)")

st.markdown("### An innovation by NikLabs, built in Dudley for Dudley.")
st.markdown("---")

uploaded_file = st.file_uploader("📂 Upload a PDF file", type="pdf")

def clean_text(text):
    replacements = {
        '“': '"', '”': '"', '‘': "'", '’': "'",
        '–': '-', '—': '-', '•': '&#8226;',
        '™': '', 'Œ': '', 'Å': '', 'â€™': "'", 'Â': '', 'é': 'e',
        'Ł': '', 'Š': ''
    }
    for bad, good in replacements.items():
        text = text.replace(bad, good)
    return text

def extract_images(pdf_path):
    doc = fitz.open(pdf_path)
    image_paths = []
    output_folder = "extracted_images"
    os.makedirs(output_folder, exist_ok=True)
    for page_index in range(len(doc)):
        for img_index, img in enumerate(doc[page_index].get_images(full=True)):
            xref = img[0]
            base_image = doc.extract_image(xref)
            image_bytes = base_image["image"]
            image_ext = base_image["ext"]
            image_filename = f"image_{page_index + 1}_{img_index + 1}.{image_ext}"
            image_path = os.path.join(output_folder, image_filename)
            with open(image_path, "wb") as image_file:
                image_file.write(image_bytes)
            image_paths.append(image_path)
    return image_paths

if uploaded_file:
    temp_path = "temp_uploaded_file.pdf"
    with open(temp_path, "wb") as f:
        f.write(uploaded_file.getbuffer())

    reader = PdfReader(temp_path)
    raw_text = ""
    for page in reader.pages:
        raw_text += page.extract_text() + "\n"

    sections = re.split(r"(?<=\n)(\d+\.\s+[^\n]+)", raw_text)
    structured_sections = []
    i = 0
    while i < len(sections) - 1:
        if re.match(r"\d+\.\s+", sections[i]):
            title = sections[i].strip()
            content = sections[i + 1].strip()
            structured_sections.append((title, content))
            i += 2
        else:
            i += 1

    toc = "<h2>Table of Contents</h2>\n<ul>\n"
    html_output = ""
    plain_output = ""
    full_text = ""

    for idx, (title, content) in enumerate(structured_sections):
        anchor = f"section{idx + 1}"
        toc += f'  <li><a href="#{anchor}">{clean_text(title)}</a></li>\n'
        cleaned_content = clean_text(content)
        full_text += cleaned_content + "\n"
        paragraphs = re.split(r'\n\s*\n|(?<=[.?!])\s*\n', cleaned_content)
        wrapped_paragraphs = ''.join([f"<p>{para.strip()}</p>\n" for para in paragraphs if para.strip()])
        html_output += f'<h2 id="{anchor}">{clean_text(title)}</h2>\n{wrapped_paragraphs}'
        plain_output += f"## {clean_text(title)}\n" + cleaned_content + "\n\n"

    toc += "</ul>"
    full_output = f"{toc}\n{html_output}\n<p><a href='#' download>Download the original PDF</a></p>"

    st.subheader("🧠 Readability Check")
    reading_age = textstat.flesch_kincaid_grade(full_text)
    ease_score = textstat.flesch_reading_ease(full_text)
    st.markdown(f"**Flesch–Kincaid Reading Age:** {reading_age:.1f} years")
    st.markdown(f"**Flesch Reading Ease Score:** {ease_score:.1f}")
    if ease_score < 60:
        st.warning("⚠️ This document may be too complex for some readers.")

    st.subheader("♿ Accessibility Notes")
    if not structured_sections:
        st.error("❌ No structured headings found.")
    else:
        st.success(f"✅ {len(structured_sections)} top-level sections detected as <h2> blocks.")
        st.info("⚠️ Check heading nesting manually if you include subheadings later.")

    st.subheader("📋 Generated HTML")
    st.code(full_output, language="html")
    st.download_button("⬇️ Download HTML", full_output, file_name="converted_output.html", mime="text/html")

    st.subheader("✍️ Export to Hemingway")
    st.download_button("⬇️ Download for Hemingway", plain_output, file_name="hemingway_export.txt", mime="text/plain")

    st.subheader("🖼️ Extracted Images")
    extracted = extract_images(temp_path)
    if extracted:
        for img in extracted:
            with open(img, "rb") as file:
                st.download_button(f"Download {os.path.basename(img)}", file.read(), file_name=os.path.basename(img))
    else:
        st.info("No images found in this PDF.")

# --- Paste Hemingway-edited content ---
st.subheader("🔁 Paste Hemingway-edited content")
edited_input = st.text_area("Paste your updated text from Hemingway below:")

def format_inline(text):
    text = re.sub(r'\*\*(.*?)\*\*', r'<strong>\1</strong>', text)
    text = re.sub(r'_(.*?)_', r'<em>\1</em>', text)
    return text

def flush_bullets(buffer):
    if buffer:
        ul = "<ul>\n"
        for item in buffer:
            ul += f"  <li>{format_inline(item)}</li>\n"
        ul += "</ul>\n"
        return ul
    return ""

if edited_input:
    st.markdown("### 🧩 Reconstructed HTML")
    lines = edited_input.splitlines()
    rebuilt_html = ""
    bullet_buffer = []

    for line in lines:
        stripped = line.strip()
        if not stripped:
            rebuilt_html += flush_bullets(bullet_buffer)
            bullet_buffer = []
            continue
        if stripped.startswith("### "):
            rebuilt_html += flush_bullets(bullet_buffer)
            bullet_buffer = []
            rebuilt_html += f"<h3>{format_inline(stripped[4:])}</h3>\n"
        elif stripped.startswith("## "):
            rebuilt_html += flush_bullets(bullet_buffer)
            bullet_buffer = []
            rebuilt_html += f"<h2>{format_inline(stripped[3:])}</h2>\n"
        elif stripped.startswith("- "):
            bullet_buffer.append(stripped[2:])
        else:
            rebuilt_html += flush_bullets(bullet_buffer)
            bullet_buffer = []
            rebuilt_html += f"<p>{format_inline(stripped)}</p>\n"

    rebuilt_html += flush_bullets(bullet_buffer)
    st.code(rebuilt_html, language="html")
    st.download_button("⬇️ Download Rewritten HTML", rebuilt_html, file_name="rewritten_output.html", mime="text/html")

st.markdown("---")
st.markdown("<p style='text-align: center; font-size: 0.9em;'>Built with ♥ by NikLabs for Dudley Council – <strong>Ultra Beta version</strong></p>", unsafe_allow_html=True)
