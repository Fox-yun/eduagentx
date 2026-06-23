import os
from langchain_core.documents import Document
from langchain_community.document_loaders import PyPDFLoader, TextLoader, UnstructuredMarkdownLoader
import charset_normalizer

class DocumentParsingError(Exception):
    pass

def parse_pdf(filepath: str) -> list[Document]:
    try:
        loader = PyPDFLoader(filepath)
        return loader.load()
    except Exception as e:
        raise DocumentParsingError(f"Failed to parse PDF: {e}")

def parse_txt(filepath: str) -> list[Document]:
    # Detect encoding first
    with open(filepath, 'rb') as f:
        raw_data = f.read(10000)
        result = charset_normalizer.detect(raw_data)
        encoding = result['encoding'] or 'utf-8'

    try:
        loader = TextLoader(filepath, encoding=encoding)
        return loader.load()
    except Exception as e:
        # Fallback to gb18030
        try:
            loader = TextLoader(filepath, encoding='gb18030')
            return loader.load()
        except Exception as fallback_e:
            raise DocumentParsingError(f"Failed to parse TXT with both {encoding} and gb18030: {fallback_e}")

def parse_markdown(filepath: str) -> list[Document]:
    try:
        # We can use standard text loader for markdown, but UnstructuredMarkdownLoader is better if installed.
        # Here we just use TextLoader to ensure it works without extra heavy dependencies if not present.
        # But wait, MarkdownTextSplitter later will handle the markdown structure.
        return parse_txt(filepath)
    except Exception as e:
        raise DocumentParsingError(f"Failed to parse Markdown: {e}")

def parse_document(filepath: str, extension: str) -> list[Document]:
    """
    Parses a document into Langchain Document objects based on its extension.
    """
    ext = extension.lower()
    if ext == '.pdf':
        return parse_pdf(filepath)
    elif ext == '.txt':
        return parse_txt(filepath)
    elif ext == '.md':
        return parse_markdown(filepath)
    else:
        raise DocumentParsingError(f"Unsupported file extension: {extension}")
