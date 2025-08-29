#!/usr/bin/env python3
"""
Test document generation script for creating various PDF test files.

This script generates comprehensive test PDFs for testing all aspects of the
PDF processing application including text extraction, image processing,
table detection, redaction, splitting, merging, and error handling.
"""

import os
import sys
import io
from pathlib import Path
from typing import List, Dict, Any, Optional
import argparse

# PDF generation libraries
from reportlab.pdfgen import canvas
from reportlab.lib.pagesizes import letter, A4, legal
from reportlab.lib.units import inch, cm
from reportlab.platypus import (
    SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle, 
    PageBreak, Image as ReportLabImage, Flowable
)
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.lib import colors
from reportlab.lib.enums import TA_LEFT, TA_CENTER, TA_RIGHT, TA_JUSTIFY
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont

# PIL for image generation
from PIL import Image, ImageDraw, ImageFont
import numpy as np

# PyPDF2 for PDF manipulation
from PyPDF2 import PdfWriter, PdfReader
import tempfile


class TestPDFGenerator:
    """Generator for creating various types of test PDF documents."""
    
    def __init__(self, output_dir: str):
        self.output_dir = Path(output_dir)
        self.output_dir.mkdir(parents=True, exist_ok=True)
        self.styles = getSampleStyleSheet()
        self._setup_custom_styles()
    
    def _setup_custom_styles(self):
        """Set up custom paragraph styles for different document types."""
        # Add custom styles
        self.styles.add(ParagraphStyle(
            name='CustomTitle',
            parent=self.styles['Heading1'],
            fontSize=18,
            spaceAfter=30,
            alignment=TA_CENTER
        ))
        
        self.styles.add(ParagraphStyle(
            name='Confidential',
            parent=self.styles['Normal'],
            fontSize=10,
            textColor=colors.red,
            alignment=TA_CENTER
        ))
        
        self.styles.add(ParagraphStyle(
            name='Footer',
            parent=self.styles['Normal'],
            fontSize=8,
            textColor=colors.grey
        ))

    def generate_simple_text_pdf(self, filename: str = "simple_text.pdf") -> Path:
        """Generate a simple text-only PDF for basic testing."""
        output_path = self.output_dir / filename
        
        doc = SimpleDocTemplate(str(output_path), pagesize=letter)
        story = []
        
        # Title
        story.append(Paragraph("Simple Text Document", self.styles['CustomTitle']))
        story.append(Spacer(1, 12))
        
        # Content with various data types for redaction testing
        content = [
            "This is a simple test document containing various types of information.",
            "",
            "Contact Information:",
            "Email: john.doe@example.com",
            "Phone: (555) 123-4567",
            "Alternative Phone: 555-987-6543",
            "Fax: 1-800-555-0199",
            "",
            "Personal Information:",
            "SSN: 123-45-6789",
            "Driver's License: D123456789",
            "Date of Birth: 01/15/1985",
            "Address: 123 Main Street, Anytown, ST 12345",
            "",
            "Financial Information:",
            "Account Number: 9876543210",
            "Routing Number: 021000021",
            "Credit Card: 4532-1234-5678-9012",
            "",
            "Medical Information:",
            "Patient ID: P-12345",
            "Medical Record Number: MRN-987654",
            "Insurance ID: INS123456789",
            "",
            "Additional test content for fuzzy matching:",
            "Contact jane.smith@company.org for technical support.",
            "Call our support line at (800) 555-HELP",
            "Confidential document - do not distribute",
            "Social Security Number: 987-65-4321",
            "",
            "This document contains sensitive information that should be redacted.",
            "For questions, email support@testcompany.com or call 555-SUPPORT."
        ]
        
        for line in content:
            if line:
                story.append(Paragraph(line, self.styles['Normal']))
            story.append(Spacer(1, 6))
        
        doc.build(story)
        return output_path

    def generate_multi_page_pdf(self, filename: str = "multi_page.pdf", pages: int = 5) -> Path:
        """Generate a multi-page PDF document for testing pagination."""
        output_path = self.output_dir / filename
        
        doc = SimpleDocTemplate(str(output_path), pagesize=A4)
        story = []
        
        for page_num in range(1, pages + 1):
            # Page title
            story.append(Paragraph(f"Page {page_num}", self.styles['CustomTitle']))
            story.append(Spacer(1, 20))
            
            # Page content
            story.append(Paragraph(f"Content for page {page_num}", self.styles['Heading2']))
            story.append(Spacer(1, 12))
            
            # Lorem ipsum style content with embedded sensitive data
            content = [
                f"This is page {page_num} of the multi-page test document.",
                f"Page {page_num} contains unique content for testing page-specific operations.",
                "",
                f"Page {page_num} Contact: page{page_num}@example.com",
                f"Page {page_num} Phone: 555-{page_num:03d}-{page_num:04d}",
                f"Page {page_num} ID: PG-{page_num:05d}",
                "",
                "Lorem ipsum dolor sit amet, consectetur adipiscing elit. Sed do eiusmod tempor incididunt ut labore et dolore magna aliqua.",
                "Ut enim ad minim veniam, quis nostrud exercitation ullamco laboris nisi ut aliquip ex ea commodo consequat.",
                "Duis aute irure dolor in reprehenderit in voluptate velit esse cillum dolore eu fugiat nulla pariatur.",
                "",
                "Common footer information appears on all pages:",
                "Document ID: DOC-123456",
                "Generated on: 2024-01-01",
                "Classification: Confidential"
            ]
            
            for line in content:
                if line:
                    story.append(Paragraph(line, self.styles['Normal']))
                story.append(Spacer(1, 6))
            
            # Add page break except for last page
            if page_num < pages:
                story.append(PageBreak())
        
        doc.build(story)
        return output_path

    def generate_table_pdf(self, filename: str = "table_document.pdf") -> Path:
        """Generate a PDF with tables for table extraction testing."""
        output_path = self.output_dir / filename
        
        doc = SimpleDocTemplate(str(output_path), pagesize=letter)
        story = []
        
        # Title
        story.append(Paragraph("Document with Tables", self.styles['CustomTitle']))
        story.append(Spacer(1, 20))
        
        # Employee table
        story.append(Paragraph("Employee Information", self.styles['Heading2']))
        story.append(Spacer(1, 12))
        
        employee_data = [
            ['Employee ID', 'Name', 'Department', 'Email', 'Phone', 'Salary'],
            ['EMP001', 'John Doe', 'Engineering', 'john.doe@company.com', '555-0101', '$75,000'],
            ['EMP002', 'Jane Smith', 'Marketing', 'jane.smith@company.com', '555-0102', '$68,000'],
            ['EMP003', 'Bob Johnson', 'Sales', 'bob.johnson@company.com', '555-0103', '$72,000'],
            ['EMP004', 'Alice Brown', 'HR', 'alice.brown@company.com', '555-0104', '$65,000'],
            ['EMP005', 'Charlie Wilson', 'Finance', 'charlie.wilson@company.com', '555-0105', '$80,000'],
        ]
        
        employee_table = Table(employee_data)
        employee_table.setStyle(TableStyle([
            ('BACKGROUND', (0, 0), (-1, 0), colors.grey),
            ('TEXTCOLOR', (0, 0), (-1, 0), colors.whitesmoke),
            ('ALIGN', (0, 0), (-1, -1), 'CENTER'),
            ('FONTNAME', (0, 0), (-1, 0), 'Helvetica-Bold'),
            ('FONTSIZE', (0, 0), (-1, 0), 10),
            ('BOTTOMPADDING', (0, 0), (-1, 0), 12),
            ('BACKGROUND', (0, 1), (-1, -1), colors.beige),
            ('GRID', (0, 0), (-1, -1), 1, colors.black),
            ('FONTSIZE', (0, 1), (-1, -1), 8),
        ]))
        
        story.append(employee_table)
        story.append(Spacer(1, 30))
        
        # Financial data table
        story.append(Paragraph("Quarterly Financial Data", self.styles['Heading2']))
        story.append(Spacer(1, 12))
        
        financial_data = [
            ['Quarter', 'Revenue', 'Expenses', 'Profit', 'Growth %'],
            ['Q1 2023', '$1,250,000', '$890,000', '$360,000', '12.5%'],
            ['Q2 2023', '$1,380,000', '$920,000', '$460,000', '15.2%'],
            ['Q3 2023', '$1,520,000', '$980,000', '$540,000', '18.7%'],
            ['Q4 2023', '$1,680,000', '$1,050,000', '$630,000', '22.1%'],
        ]
        
        financial_table = Table(financial_data)
        financial_table.setStyle(TableStyle([
            ('BACKGROUND', (0, 0), (-1, 0), colors.darkblue),
            ('TEXTCOLOR', (0, 0), (-1, 0), colors.white),
            ('ALIGN', (0, 0), (-1, -1), 'CENTER'),
            ('FONTNAME', (0, 0), (-1, 0), 'Helvetica-Bold'),
            ('FONTSIZE', (0, 0), (-1, 0), 10),
            ('BOTTOMPADDING', (0, 0), (-1, 0), 12),
            ('BACKGROUND', (0, 1), (-1, -1), colors.lightblue),
            ('GRID', (0, 0), (-1, -1), 1, colors.black),
            ('FONTSIZE', (0, 1), (-1, -1), 9),
        ]))
        
        story.append(financial_table)
        story.append(Spacer(1, 30))
        
        # Complex nested table
        story.append(Paragraph("Complex Table Structure", self.styles['Heading2']))
        story.append(Spacer(1, 12))
        
        complex_data = [
            ['Product Category', 'Product Name', 'Q1 Sales', 'Q2 Sales', 'Total', 'Market Share'],
            ['Electronics', 'Smartphone Pro', '$450,000', '$520,000', '$970,000', '15.2%'],
            ['', 'Tablet Ultra', '$320,000', '$380,000', '$700,000', '11.0%'],
            ['', 'Laptop Series X', '$680,000', '$750,000', '$1,430,000', '22.4%'],
            ['Home & Garden', 'Smart Thermostat', '$180,000', '$210,000', '$390,000', '6.1%'],
            ['', 'Garden Tools Set', '$120,000', '$140,000', '$260,000', '4.1%'],
            ['Clothing', 'Winter Collection', '$290,000', '$180,000', '$470,000', '7.4%'],
            ['', 'Summer Collection', '$150,000', '$340,000', '$490,000', '7.7%'],
        ]
        
        complex_table = Table(complex_data)
        complex_table.setStyle(TableStyle([
            ('BACKGROUND', (0, 0), (-1, 0), colors.green),
            ('TEXTCOLOR', (0, 0), (-1, 0), colors.white),
            ('ALIGN', (0, 0), (-1, -1), 'CENTER'),
            ('FONTNAME', (0, 0), (-1, 0), 'Helvetica-Bold'),
            ('FONTSIZE', (0, 0), (-1, 0), 9),
            ('GRID', (0, 0), (-1, -1), 1, colors.black),
            ('FONTSIZE', (0, 1), (-1, -1), 8),
            ('SPAN', (0, 1), (0, 3)),  # Span Electronics category
            ('SPAN', (0, 4), (0, 5)),  # Span Home & Garden category
            ('SPAN', (0, 6), (0, 7)),  # Span Clothing category
        ]))
        
        story.append(complex_table)
        
        doc.build(story)
        return output_path

    def generate_image_pdf(self, filename: str = "image_document.pdf") -> Path:
        """Generate a PDF with embedded images for image extraction testing."""
        output_path = self.output_dir / filename
        
        # Create temporary images
        temp_images = []
        
        # Create a simple chart image
        chart_img = Image.new('RGB', (400, 300), 'white')
        draw = ImageDraw.Draw(chart_img)
        
        # Draw a simple bar chart
        bars = [(50, 250), (100, 200), (150, 180), (200, 220), (250, 160)]
        for i, (x, y) in enumerate(bars):
            draw.rectangle([x, y, x+30, 250], fill=f'#{i*50:02x}{(5-i)*50:02x}80')
            draw.text((x+5, 260), f'Q{i+1}', fill='black')
        
        draw.text((150, 20), 'Sales Chart', fill='black')
        
        chart_path = tempfile.NamedTemporaryFile(suffix='.png', delete=False)
        chart_img.save(chart_path.name, 'PNG')
        temp_images.append(chart_path.name)
        
        # Create a logo-like image
        logo_img = Image.new('RGB', (200, 100), 'blue')
        draw = ImageDraw.Draw(logo_img)
        draw.text((50, 40), 'COMPANY', fill='white')
        
        logo_path = tempfile.NamedTemporaryFile(suffix='.png', delete=False)
        logo_img.save(logo_path.name, 'PNG')
        temp_images.append(logo_path.name)
        
        # Create document
        doc = SimpleDocTemplate(str(output_path), pagesize=letter)
        story = []
        
        # Title
        story.append(Paragraph("Document with Images", self.styles['CustomTitle']))
        story.append(Spacer(1, 20))
        
        # Logo
        story.append(Paragraph("Company Logo", self.styles['Heading2']))
        story.append(Spacer(1, 12))
        logo = ReportLabImage(logo_path.name, width=200, height=100)
        story.append(logo)
        story.append(Spacer(1, 20))
        
        # Text content
        story.append(Paragraph("Annual Report Summary", self.styles['Heading2']))
        story.append(Spacer(1, 12))
        
        content = [
            "This annual report contains both textual information and visual charts.",
            "The following chart shows our quarterly performance:",
            "Contact: investor.relations@company.com",
            "Phone: 1-800-INVESTOR (1-800-468-3786)",
        ]
        
        for line in content:
            story.append(Paragraph(line, self.styles['Normal']))
            story.append(Spacer(1, 6))
        
        story.append(Spacer(1, 20))
        
        # Chart
        story.append(Paragraph("Performance Chart", self.styles['Heading2']))
        story.append(Spacer(1, 12))
        chart = ReportLabImage(chart_path.name, width=400, height=300)
        story.append(chart)
        
        doc.build(story)
        
        # Cleanup temporary files
        for temp_file in temp_images:
            try:
                os.unlink(temp_file)
            except OSError:
                pass
        
        return output_path

    def generate_large_pdf(self, filename: str = "large_document.pdf", pages: int = 100) -> Path:
        """Generate a large PDF document for performance testing."""
        output_path = self.output_dir / filename
        
        doc = SimpleDocTemplate(str(output_path), pagesize=letter)
        story = []
        
        for page_num in range(1, pages + 1):
            story.append(Paragraph(f"Page {page_num} - Performance Test Document", self.styles['CustomTitle']))
            story.append(Spacer(1, 20))
            
            # Generate substantial content per page
            content_paragraphs = [
                f"This is page {page_num} of a large document designed for performance testing.",
                "Lorem ipsum dolor sit amet, consectetur adipiscing elit, sed do eiusmod tempor incididunt ut labore et dolore magna aliqua. Ut enim ad minim veniam, quis nostrud exercitation ullamco laboris nisi ut aliquip ex ea commodo consequat. Duis aute irure dolor in reprehenderit in voluptate velit esse cillum dolore eu fugiat nulla pariatur.",
                "Sed ut perspiciatis unde omnis iste natus error sit voluptatem accusantium doloremque laudantium, totam rem aperiam, eaque ipsa quae ab illo inventore veritatis et quasi architecto beatae vitae dicta sunt explicabo. Nemo enim ipsam voluptatem quia voluptas sit aspernatur aut odit aut fugit.",
                f"Page {page_num} contains embedded contact information:",
                f"Email: page{page_num}@performance-test.com",
                f"Phone: 555-{page_num:03d}-{(page_num * 7) % 10000:04d}",
                f"Reference ID: PERF-{page_num:05d}",
                "At vero eos et accusamus et iusto odio dignissimos ducimus qui blanditiis praesentium voluptatum deleniti atque corrupti quos dolores et quas molestias excepturi sint occaecati cupiditate non provident, similique sunt in culpa qui officia deserunt mollitia animi.",
                "But I must explain to you how all this mistaken idea of denouncing pleasure and praising pain was born and I will give you a complete account of the system, and expound the actual teachings of the great explorer of the truth, the master-builder of human happiness.",
                f"Performance metrics for page {page_num}: Processing time should be measured and optimized.",
            ]
            
            for para in content_paragraphs:
                story.append(Paragraph(para, self.styles['Normal']))
                story.append(Spacer(1, 8))
            
            # Add a table every 10 pages
            if page_num % 10 == 0:
                table_data = [
                    ['Metric', 'Value', 'Target', 'Status'],
                    ['Processing Time', f'{page_num * 0.1:.1f}s', '5.0s', 'Good'],
                    ['Memory Usage', f'{page_num * 2}MB', '500MB', 'Good'],
                    ['Page Count', str(page_num), str(pages), 'Progress'],
                ]
                
                table = Table(table_data)
                table.setStyle(TableStyle([
                    ('BACKGROUND', (0, 0), (-1, 0), colors.grey),
                    ('TEXTCOLOR', (0, 0), (-1, 0), colors.white),
                    ('ALIGN', (0, 0), (-1, -1), 'CENTER'),
                    ('FONTNAME', (0, 0), (-1, 0), 'Helvetica-Bold'),
                    ('FONTSIZE', (0, 0), (-1, 0), 10),
                    ('GRID', (0, 0), (-1, -1), 1, colors.black),
                ]))
                
                story.append(Spacer(1, 20))
                story.append(table)
            
            if page_num < pages:
                story.append(PageBreak())
        
        doc.build(story)
        return output_path

    def generate_corrupted_pdf(self, filename: str = "corrupted.pdf") -> Path:
        """Generate a corrupted PDF file for error testing."""
        output_path = self.output_dir / filename
        
        # First create a valid PDF
        buffer = io.BytesIO()
        c = canvas.Canvas(buffer, pagesize=letter)
        c.drawString(100, 750, "This PDF will be corrupted for testing purposes")
        c.drawString(100, 700, "Contact: test@corrupted-pdf.com")
        c.drawString(100, 650, "Phone: 555-CORRUPT")
        c.save()
        
        # Get the PDF data and corrupt it
        pdf_data = buffer.getvalue()
        
        # Corrupt by truncating at 70% of original size
        corrupted_size = int(len(pdf_data) * 0.7)
        corrupted_data = pdf_data[:corrupted_size]
        
        with open(output_path, 'wb') as f:
            f.write(corrupted_data)
        
        return output_path

    def generate_password_protected_pdf(self, filename: str = "password_protected.pdf", password: str = "testpass123") -> Path:
        """Generate a password-protected PDF for security testing."""
        output_path = self.output_dir / filename
        
        # Create a temporary unprotected PDF
        temp_buffer = io.BytesIO()
        c = canvas.Canvas(temp_buffer, pagesize=letter)
        c.drawString(100, 750, "This is a password-protected document")
        c.drawString(100, 700, "Password: testpass123")
        c.drawString(100, 650, "Confidential Information:")
        c.drawString(100, 600, "Employee ID: EMP-SECRET-001")
        c.drawString(100, 550, "Email: confidential@secret-company.com")
        c.drawString(100, 500, "SSN: 999-99-9999")
        c.save()
        
        temp_buffer.seek(0)
        
        # Read and encrypt the PDF
        reader = PdfReader(temp_buffer)
        writer = PdfWriter()
        
        for page in reader.pages:
            writer.add_page(page)
        
        writer.encrypt(password)
        
        with open(output_path, 'wb') as output_file:
            writer.write(output_file)
        
        return output_path

    def generate_mixed_content_pdf(self, filename: str = "mixed_content.pdf") -> Path:
        """Generate a PDF with mixed content types for comprehensive testing."""
        output_path = self.output_dir / filename
        
        # Create temporary image
        temp_img = Image.new('RGB', (300, 200), 'lightblue')
        draw = ImageDraw.Draw(temp_img)
        draw.text((100, 90), 'Mixed Content', fill='darkblue')
        
        temp_img_path = tempfile.NamedTemporaryFile(suffix='.png', delete=False)
        temp_img.save(temp_img_path.name, 'PNG')
        
        doc = SimpleDocTemplate(str(output_path), pagesize=letter)
        story = []
        
        # Title
        story.append(Paragraph("Mixed Content Document", self.styles['CustomTitle']))
        story.append(Spacer(1, 20))
        
        # Text content with sensitive data
        story.append(Paragraph("Confidential Business Information", self.styles['Heading2']))
        story.append(Spacer(1, 12))
        
        text_content = [
            "This document contains mixed content types for comprehensive testing.",
            "CONFIDENTIAL - Do not distribute without authorization.",
            "",
            "Primary Contact: director@mixedcontent-corp.com",
            "Secondary Contact: admin@mixedcontent-corp.com", 
            "Emergency Contact: emergency@mixedcontent-corp.com",
            "Phone Numbers: (555) 100-2000, (555) 100-2001, (555) 100-2002",
            "",
            "Account Information:",
            "Primary Account: 1234567890123456",
            "Secondary Account: 6543210987654321",
            "Routing: 021000021",
        ]
        
        for line in text_content:
            if line:
                story.append(Paragraph(line, self.styles['Normal']))
            story.append(Spacer(1, 6))
        
        story.append(Spacer(1, 20))
        
        # Image
        image = ReportLabImage(temp_img_path.name, width=300, height=200)
        story.append(image)
        story.append(Spacer(1, 20))
        
        # Table
        story.append(Paragraph("Contact Directory", self.styles['Heading2']))
        story.append(Spacer(1, 12))
        
        contact_data = [
            ['Department', 'Contact Person', 'Email', 'Phone', 'Extension'],
            ['Sales', 'John Sales', 'sales@company.com', '555-SALES-01', '101'],
            ['Support', 'Jane Support', 'support@company.com', '555-HELP-02', '102'],
            ['Billing', 'Bob Billing', 'billing@company.com', '555-BILL-03', '103'],
            ['Legal', 'Alice Legal', 'legal@company.com', '555-LAW-004', '104'],
        ]
        
        contact_table = Table(contact_data)
        contact_table.setStyle(TableStyle([
            ('BACKGROUND', (0, 0), (-1, 0), colors.darkgreen),
            ('TEXTCOLOR', (0, 0), (-1, 0), colors.white),
            ('ALIGN', (0, 0), (-1, -1), 'CENTER'),
            ('FONTNAME', (0, 0), (-1, 0), 'Helvetica-Bold'),
            ('FONTSIZE', (0, 0), (-1, -1), 8),
            ('GRID', (0, 0), (-1, -1), 1, colors.black),
        ]))
        
        story.append(contact_table)
        story.append(Spacer(1, 30))
        
        # Additional text with various formats
        story.append(Paragraph("Additional Information", self.styles['Heading2']))
        story.append(Spacer(1, 12))
        
        additional_content = [
            "This section contains additional information in various formats:",
            "• Bullet point with email: info@bullets.com",
            "• Bullet point with phone: 1-800-BULLETS",
            "• Bullet point with ID: BULLET-12345",
            "",
            "Numbered list:",
            "1. First item - contact: first@numbered.com",
            "2. Second item - phone: (555) 222-2222", 
            "3. Third item - reference: NUM-67890",
        ]
        
        for line in additional_content:
            if line:
                story.append(Paragraph(line, self.styles['Normal']))
            story.append(Spacer(1, 6))
        
        # Confidential footer
        story.append(Spacer(1, 30))
        story.append(Paragraph("CONFIDENTIAL DOCUMENT - AUTHORIZED PERSONNEL ONLY", self.styles['Confidential']))
        
        doc.build(story)
        
        # Cleanup
        try:
            os.unlink(temp_img_path.name)
        except OSError:
            pass
        
        return output_path

    def generate_all_test_pdfs(self) -> List[Path]:
        """Generate all test PDF documents."""
        generated_files = []
        
        print("Generating test PDF documents...")
        
        # Basic documents
        print("  Creating simple text PDF...")
        generated_files.append(self.generate_simple_text_pdf())
        
        print("  Creating multi-page PDF...")
        generated_files.append(self.generate_multi_page_pdf())
        
        print("  Creating table document...")
        generated_files.append(self.generate_table_pdf())
        
        print("  Creating image document...")
        generated_files.append(self.generate_image_pdf())
        
        print("  Creating mixed content document...")
        generated_files.append(self.generate_mixed_content_pdf())
        
        # Large document for performance testing
        print("  Creating large performance test document (this may take a while)...")
        generated_files.append(self.generate_large_pdf())
        
        # Error testing documents
        print("  Creating corrupted PDF...")
        generated_files.append(self.generate_corrupted_pdf())
        
        print("  Creating password-protected PDF...")
        generated_files.append(self.generate_password_protected_pdf())
        
        # Additional specialized documents
        print("  Creating additional specialized documents...")
        
        # Small multi-page for splitting tests
        generated_files.append(self.generate_multi_page_pdf("split_test.pdf", pages=10))
        
        # Multiple documents for merging tests
        for i in range(1, 4):
            generated_files.append(self.generate_simple_text_pdf(f"merge_part_{i}.pdf"))
        
        # Document with extensive tables
        generated_files.append(self.generate_table_pdf("extensive_tables.pdf"))
        
        # Document with many images
        generated_files.append(self.generate_image_pdf("image_heavy.pdf"))
        
        print(f"Generated {len(generated_files)} test PDF documents in {self.output_dir}")
        return generated_files


def main():
    """Main function for command-line usage."""
    parser = argparse.ArgumentParser(description="Generate test PDF documents")
    parser.add_argument(
        "--output-dir", 
        default="./test_documents", 
        help="Output directory for generated PDFs"
    )
    parser.add_argument(
        "--document-type",
        choices=["all", "simple", "multi-page", "table", "image", "large", "corrupted", "protected", "mixed"],
        default="all",
        help="Type of document to generate"
    )
    
    args = parser.parse_args()
    
    generator = TestPDFGenerator(args.output_dir)
    
    if args.document_type == "all":
        generated_files = generator.generate_all_test_pdfs()
    elif args.document_type == "simple":
        generated_files = [generator.generate_simple_text_pdf()]
    elif args.document_type == "multi-page":
        generated_files = [generator.generate_multi_page_pdf()]
    elif args.document_type == "table":
        generated_files = [generator.generate_table_pdf()]
    elif args.document_type == "image":
        generated_files = [generator.generate_image_pdf()]
    elif args.document_type == "large":
        generated_files = [generator.generate_large_pdf()]
    elif args.document_type == "corrupted":
        generated_files = [generator.generate_corrupted_pdf()]
    elif args.document_type == "protected":
        generated_files = [generator.generate_password_protected_pdf()]
    elif args.document_type == "mixed":
        generated_files = [generator.generate_mixed_content_pdf()]
    
    print("\nGenerated files:")
    for file_path in generated_files:
        file_size = os.path.getsize(file_path) / 1024  # KB
        print(f"  {file_path.name} ({file_size:.1f} KB)")


if __name__ == "__main__":
    main()