#!/usr/bin/env python3
"""
NikLabs: Dudley DocLiberator (Beta)
An innovation by NikLabs, built in Dudley for Dudley.

This application converts PDF documents to accessible HTML format
with automatic linking, readability analysis, and optional AI rewriting.
"""

import streamlit as st
from PyPDF2 import PdfReader
import re
import textstat
from openai import OpenAI
import base64
import os
import tempfile

st.set_page_config(page_title="NikLabs: Dudley DocLiberator (Beta)", layout="centered")

st.title("NikLabs: Dudley DocLiberator (Beta)")
st.markdown("### An innovation by NikLabs, built in Dudley for Dudley.")
st.markdown("---")

# File size limit (200MB)
MAX_FILE_SIZE = 200 * 1024 * 1024

uploaded_file = st.file_uploader("📂 Upload a PDF file", type="pdf", help="Maximum file size: 200MB")
use_openai = st.checkbox("Rewrite using OpenAI for reading age 9")
api_key = st.text_input("Enter your OpenAI API key", type="password", help="Your API key is not stored") if use_openai else None

def validate_file(uploaded_file):
    """Validate uploaded file size and type"""
    if uploaded_file.size > MAX_FILE_SIZE:
        st.error(f"File too large! Maximum size is {MAX_FILE_SIZE / (1024*1024):.0f}MB. Your file is {uploaded_file.size / (1024*1024):.1f}MB.")
        return False
    return True

def clean_text(text):
    """Clean up common PDF extraction artifacts"""
    replacements = {
        '"': '"', '"': '"', ''': "'", ''': "'",
        '–': '-', '—': '-', '•': '&#8226;',
        '™': '', 'Œ': '', 'Å': '', 'â€™': "'", 'Â': '', 'é': 'e',
        'Ł': '', 'Š': ''
    }
    for bad, good in replacements.items():
        text = text.replace(bad, good)
    
    # Remove excessive whitespace
    text = re.sub(r'\n\s*\n\s*\n', '\n\n', text)
    text = re.sub(r' +', ' ', text)
    
    return text.strip()

def validate_extracted_text(text):
    """Check if extracted text is reasonable quality"""
    if len(text.strip()) < 100:
        return False, "Document appears to be too short or mostly empty."
    
    # Check for reasonable ratio of letters to total characters
    letter_ratio = sum(c.isalpha() for c in text) / len(text) if text else 0
    if letter_ratio < 0.5:
        return False, "Document appears to contain mostly non-text content or may be corrupted."
    
    return True, ""

def auto_link(text):
    """Convert text URLs, emails, and phone numbers to clickable links"""
    import re
    
    # Find all potential linkable items with their positions
    items = []
    
    # Find emails
    for match in re.finditer(r'\b([a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,})\b', text):
        items.append((match.start(), match.end(), 'email', match.group(1)))
    
    # Find full URLs
    for match in re.finditer(r'\b(https?://[^\s<>"\']+)', text):
        items.append((match.start(), match.end(), 'url', match.group(1)))
    
    # Find www URLs
    for match in re.finditer(r'\b(www\.[a-zA-Z0-9][a-zA-Z0-9.-]*\.[a-zA-Z]{2,}(?:/[^\s<>"\']*)?)', text):
        items.append((match.start(), match.end(), 'www', match.group(1)))
    
    # Find UK domains (but not if they're part of an email)
    for match in re.finditer(r'\b([a-zA-Z0-9][a-zA-Z0-9.-]*\.(?:gov\.uk|org\.uk|co\.uk|ac\.uk)(?:/[^\s<>"\']*)?)\b', text):
        # Check if this is part of an email (has @ before it)
        start_pos = max(0, match.start() - 50)
        context = text[start_pos:match.start()]
        if '@' not in context.split()[-1] if context.split() else True:
            items.append((match.start(), match.end(), 'domain', match.group(1)))
    
    # Find phone numbers
    phone_patterns = [
        (r'\b(0\d{3}\s?\d{3}\s?\d{3,4})\b', 'phone'),
        (r'\b(0\d{4}\s?\d{5,6})\b', 'phone'),
        (r'\b(\+44\s?\d{3}\s?\d{3}\s?\d{3,4})\b', 'phone')
    ]
    
    for pattern, type_name in phone_patterns:
        for match in re.finditer(pattern, text):
            items.append((match.start(), match.end(), type_name, match.group(1)))
    
    # Sort by position and remove overlaps (keep the first/longest match)
    items.sort()
    filtered_items = []
    for item in items:
        start, end, item_type, value = item
        # Check if this overlaps with any existing item
        overlaps = False
        for existing in filtered_items:
            existing_start, existing_end = existing[0], existing[1]
            if not (end <= existing_start or start >= existing_end):
                overlaps = True
                break
        if not overlaps:
            filtered_items.append(item)
    
    # Apply links from right to left to preserve positions
    filtered_items.reverse()
    
    for start, end, item_type, value in filtered_items:
        if item_type == 'email':
            replacement = f'<a href="mailto:{value}">{value}</a>'
        elif item_type in ['url']:
            replacement = f'<a href="{value}">{value}</a>'
        elif item_type in ['www', 'domain']:
            replacement = f'<a href="http://{value}">{value}</a>'
        elif item_type == 'phone':
            clean_phone = value.replace(' ', '')
            replacement = f'<a href="tel:{clean_phone}">{value}</a>'
        else:
            continue
            
        text = text[:start] + replacement + text[end:]
    
    return text

def test_openai_connection(api_key):
    """Test if OpenAI API key works"""
    try:
        client = OpenAI(api_key=api_key)
        # Simple test call
        response = client.chat.completions.create(
            model="gpt-4o",
            messages=[{"role": "user", "content": "Hello"}],
            max_tokens=5
        )
        return True, ""
    except Exception as e:
        return False, str(e)

def rewrite_text(original_text, api_key):
    """Rewrite text for age 9 readability using OpenAI"""
    try:
        client = OpenAI(api_key=api_key)
        system_prompt = (
            "You are a writing assistant for UK local government. Rewrite the following document "
            "to achieve a reading age of 9 without sounding childish. Only simplify the wording. "
            "Do not remove or alter the [[SECTION:h2:...]] markers — they are used to preserve heading structure. "
            "Preserve paragraph breaks and structure. Use UK English. Keep all important information."
            "Do not change things for the sake of it. Retain as much of the original information and wording as you can. "
            "Avoid changing numbers, names or legal references. "
        )
        
        with st.spinner("Rewriting text with OpenAI... This may take a moment."):
            response = client.chat.completions.create(
                model="gpt-4o",
                messages=[
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": original_text}
                ],
                temperature=0.4,
            )
        return response.choices[0].message.content, None
    except Exception as e:
        return None, f"OpenAI Error: {str(e)}"

def extract_title(text):
    """Extract document title from text"""
    lines = text.splitlines()
    for line in lines:
        stripped = line.strip()
        # Look for title-like lines (all caps, reasonable length, mostly letters)
        if (
            len(stripped) >= 10
            and stripped.upper() == stripped
            and sum(c.isalpha() for c in stripped) >= 10
            and sum(c.isdigit() for c in stripped) < len(stripped) * 0.4
            and len(stripped.split()) > 2
        ):
            return stripped
    return None

def prepare_marked_text(text):
    """Prepare text with section markers for HTML conversion"""
    result = []
    title = extract_title(text)
    if title:
        text = text.replace(title, "").strip()

    # Look for numbered sections (1. 2. 3. etc.)
    match = re.search(r"(\d{1,2}\.\s+.+?)(?=\n|$)", text)
    if not match:
        # No numbered sections found, treat as single section
        return title, f"[[SECTION:h2:Document Content]]\n{text.strip()}"

    start_idx = match.start()
    if start_idx > 0:
        preamble = text[:start_idx].strip()
        if preamble:
            result.append(f"[[SECTION:h2:Introduction]]\n{preamble}")

    remaining = text[start_idx:]
    pattern = re.compile(r"(?m)^([1-9][0-9]?\.\s+.+)")
    matches = list(pattern.finditer(remaining))

    for i, match in enumerate(matches):
        heading = match.group(1).strip()
        start = match.end()
        next_start = matches[i + 1].start() if i + 1 < len(matches) else len(remaining)
        content = remaining[start:next_start].strip()
        result.append(f"[[SECTION:h2:{heading}]]\n{content}")

    return title, "\n\n".join(result)

def build_html_from_markers(text, title=None):
    """Convert marked text to HTML with table of contents"""
    blocks = re.split(r"\[\[SECTION:h2:(.*?)\]\]", text)
    html_output = ""
    toc = ""
    full_text = ""

    if title:
        html_output += f"<h1>{title}</h1>\n"

    # Build table of contents
    toc += "<h2>Table of Contents</h2>\n<ul>\n"
    for i in range(1, len(blocks), 2):
        heading = clean_text(blocks[i].strip())
        anchor = f"section{i//2+1}"
        toc += f'<li><a href="#{anchor}">{heading}</a></li>\n'
    toc += "</ul>\n"
    html_output += toc

    # Build main content
    for i in range(1, len(blocks), 2):
        heading = clean_text(blocks[i].strip())
        anchor = f"section{i//2+1}"
        body = clean_text(blocks[i+1])
        full_text += body + "\n"
        
        # Split into paragraphs
        paragraphs = re.split(r'\n\s*\n|(?<=[.?!])\s*\n', body)
        wrapped = ''.join([f"<p>{auto_link(p.strip())}</p>\n" for p in paragraphs if p.strip()])
        html_output += f'<h2 id="{anchor}">{heading}</h2>\n{wrapped}'
    
    return html_output, full_text

def generate_download_button(html_content, label, filename):
    """Generate download button for HTML content"""
    b64 = base64.b64encode(html_content.encode()).decode()
    href = f'<a href="data:file/html;base64,{b64}" download="{filename}">{label}</a>'
    st.markdown(href, unsafe_allow_html=True)

def get_readability_advice(reading_age, ease_score):
    """Provide advice based on readability scores"""
    advice = []
    
    if reading_age > 12:
        advice.append("📚 Consider using shorter sentences and simpler words")
    if ease_score < 60:
        advice.append("⚠️ Document may be difficult for general public")
    elif ease_score > 80:
        advice.append("✅ Document is easy to read")
    else:
        advice.append("👍 Document readability is reasonable")
    
    return advice

# Main application logic
if uploaded_file:
    # Validate file
    if not validate_file(uploaded_file):
        st.stop()
    
    # Show file info
    st.info(f"📄 Processing: {uploaded_file.name} ({uploaded_file.size / 1024:.1f} KB)")
    
    try:
        # Create temporary file safely
        with tempfile.NamedTemporaryFile(delete=False, suffix='.pdf') as tmp_file:
            tmp_file.write(uploaded_file.getbuffer())
            temp_path = tmp_file.name
        
        # Extract text from PDF
        with st.spinner("Extracting text from PDF..."):
            reader = PdfReader(temp_path)
            raw_text = ""
            for page_num, page in enumerate(reader.pages):
                try:
                    raw_text += page.extract_text() + "\n"
                except Exception as e:
                    st.warning(f"Could not read page {page_num + 1}: {str(e)}")
        
        # Clean up temp file
        os.unlink(temp_path)
        
        # Validate extracted text
        is_valid, error_msg = validate_extracted_text(raw_text)
        if not is_valid:
            st.error(f"❌ {error_msg}")
            st.info("💡 Try a different PDF or check if the file contains readable text.")
            st.stop()
        
        # Process text
        doc_title, marked_text = prepare_marked_text(raw_text)
        cleaned_html, full_text = build_html_from_markers(marked_text, doc_title)
        
        # Calculate word count
        word_count = len(full_text.split())
        
        # Display results
        st.success(f"✅ Successfully processed {len(reader.pages)} pages, {word_count:,} words")
        
        st.subheader("📋 Generated HTML (Code View)")
        st.code(cleaned_html, language="html")

        st.subheader("🖥 Rendered HTML Preview")
        st.markdown(cleaned_html, unsafe_allow_html=True)

        generate_download_button(cleaned_html, "⬇️ Download Cleaned HTML", "converted_output.html")

        # Readability analysis
        reading_age = textstat.flesch_kincaid_grade(full_text)
        ease_score = textstat.flesch_reading_ease(full_text)
        
        st.subheader("🧠 Readability Analysis")
        col1, col2, col3 = st.columns(3)
        
        with col1:
            st.metric("Reading Age", f"{reading_age:.1f} years")
        with col2:
            st.metric("Ease Score", f"{ease_score:.0f}/100")
        with col3:
            st.metric("Word Count", f"{word_count:,}")
        
        # Readability advice
        advice = get_readability_advice(reading_age, ease_score)
        for tip in advice:
            st.info(tip)

        # OpenAI rewriting
        if use_openai and api_key:
            # Test API key first
            api_works, api_error = test_openai_connection(api_key)
            if not api_works:
                st.error(f"❌ OpenAI API Error: {api_error}")
                st.info("💡 Check your API key and try again.")
            else:
                st.subheader("✍️ Rewritten for Age 9 Readability")
                
                rewritten, rewrite_error = rewrite_text(marked_text, api_key)
                if rewrite_error:
                    st.error(f"❌ {rewrite_error}")
                else:
                    rewritten_html, rewritten_full_text = build_html_from_markers(rewritten, doc_title)
                    
                    # Show improvement
                    new_reading_age = textstat.flesch_kincaid_grade(rewritten_full_text)
                    new_ease_score = textstat.flesch_reading_ease(rewritten_full_text)
                    
                    col1, col2 = st.columns(2)
                    with col1:
                        st.metric("New Reading Age", f"{new_reading_age:.1f} years", 
                                delta=f"{new_reading_age - reading_age:.1f}")
                    with col2:
                        st.metric("New Ease Score", f"{new_ease_score:.0f}/100", 
                                delta=f"{new_ease_score - ease_score:.0f}")
                    
                    st.code(rewritten_html, language="html")
                    st.markdown("🖥 Rendered Rewritten HTML")
                    st.markdown(rewritten_html, unsafe_allow_html=True)
                    generate_download_button(rewritten_html, "⬇️ Download Rewritten HTML", "rewritten_output.html")

    except Exception as e:
        st.error(f"❌ Error processing PDF: {str(e)}")
        st.info("💡 Try a different PDF file or contact support if the problem persists.")

st.markdown("---")
st.markdown("<p style='text-align: center; font-size: 0.9em;'>Built with ♥ by NikLabs for Dudley Council – <strong>Beta version</strong></p>", unsafe_allow_html=True)