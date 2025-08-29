# Test Documents Directory

This directory contains test PDF documents for comprehensive testing of the PDF processing application. The test documents are designed to cover all aspects of PDF processing including text extraction, image processing, table detection, redaction, splitting, merging, and error handling scenarios.

## Overview

The test documents in this directory are generated using the `generate_test_pdfs.py` script and provide realistic scenarios for testing all components of the PDF processing pipeline. Each document is designed to test specific functionality while also containing data suitable for cross-functional testing.

## Document Types

### Basic Test Documents

#### `simple_text.pdf`
- **Purpose**: Basic text extraction and redaction testing
- **Content**: Simple text with various types of sensitive information
- **Contains**: Email addresses, phone numbers, SSNs, addresses, financial data
- **Size**: ~10 KB
- **Pages**: 1
- **Use Cases**:
  - Basic text extraction testing
  - Simple redaction workflows
  - PDF validation testing
  - API endpoint testing

#### `multi_page.pdf`
- **Purpose**: Multi-page document testing and pagination
- **Content**: 5 pages with unique content per page
- **Contains**: Page-specific contact information and common footers
- **Size**: ~25 KB
- **Pages**: 5
- **Use Cases**:
  - Page-range splitting testing
  - Multi-page text extraction
  - Page navigation testing
  - Bookmark-based operations

#### `table_document.pdf`
- **Purpose**: Table detection and extraction testing
- **Content**: Multiple tables with different structures
- **Contains**: Employee data, financial information, complex nested tables
- **Size**: ~30 KB
- **Pages**: 1
- **Use Cases**:
  - Table extraction with camelot-py and tabula-py
  - CSV export functionality
  - Structured data extraction
  - Table validation and filtering

#### `image_document.pdf`
- **Purpose**: Image extraction and processing testing
- **Content**: Embedded images including charts and logos
- **Contains**: Generated chart images and company logo graphics
- **Size**: ~50 KB
- **Pages**: 1
- **Use Cases**:
  - Image extraction testing
  - Format conversion (PNG, JPG)
  - Image quality optimization
  - OCR processing on embedded images

#### `mixed_content.pdf`
- **Purpose**: Comprehensive testing with all content types
- **Content**: Text, images, tables, and various formatting
- **Contains**: Mixed sensitive data across different content types
- **Size**: ~40 KB
- **Pages**: 1
- **Use Cases**:
  - Comprehensive extraction testing
  - Multi-format output generation
  - Complex redaction scenarios
  - Integration testing

### Specialized Test Documents

#### `large_document.pdf`
- **Purpose**: Performance and scalability testing
- **Content**: 100 pages with substantial content per page
- **Contains**: Lorem ipsum text with embedded sensitive data
- **Size**: ~2-5 MB
- **Pages**: 100
- **Use Cases**:
  - Performance benchmarking
  - Memory usage testing
  - Large file upload testing
  - Timeout and progress tracking testing
  - Stress testing with concurrent operations

#### `split_test.pdf`
- **Purpose**: PDF splitting functionality testing
- **Content**: 10 pages designed for splitting operations
- **Contains**: Clear page boundaries and split markers
- **Size**: ~50 KB
- **Pages**: 10
- **Use Cases**:
  - Page range splitting
  - Pattern-based splitting
  - Bookmark-based splitting
  - Split validation testing

#### `merge_part_1.pdf`, `merge_part_2.pdf`, `merge_part_3.pdf`
- **Purpose**: PDF merging functionality testing
- **Content**: Individual documents designed to be merged
- **Contains**: Complementary content with different metadata
- **Size**: ~10 KB each
- **Pages**: 1 each
- **Use Cases**:
  - Multi-document merging
  - Bookmark preservation testing
  - Metadata handling during merge
  - Order validation in merged output

### Error Handling Documents

#### `corrupted.pdf`
- **Purpose**: Error handling and validation testing
- **Content**: Intentionally corrupted PDF data
- **Contains**: Truncated PDF structure
- **Size**: Variable (truncated)
- **Pages**: Invalid
- **Use Cases**:
  - Error handling testing
  - Input validation testing
  - Graceful failure scenarios
  - User error message testing

#### `password_protected.pdf`
- **Purpose**: Security and password handling testing
- **Content**: Password-encrypted PDF document
- **Contains**: Confidential information (password: `testpass123`)
- **Size**: ~15 KB
- **Pages**: 1
- **Use Cases**:
  - Password handling testing
  - Security validation
  - Authentication workflows
  - Error handling for protected files

### Specialized Content Documents

#### `extensive_tables.pdf`
- **Purpose**: Advanced table processing testing
- **Content**: Multiple complex tables with various structures
- **Contains**: Financial data, employee records, nested tables
- **Size**: ~40 KB
- **Pages**: 1
- **Use Cases**:
  - Complex table detection algorithms
  - Multiple table extraction
  - Table structure preservation
  - Advanced CSV export scenarios

#### `image_heavy.pdf`
- **Purpose**: Image-intensive processing testing
- **Content**: Multiple embedded images of different types
- **Contains**: Charts, logos, diagrams, photographs
- **Size**: ~100 KB
- **Pages**: 1
- **Use Cases**:
  - Bulk image extraction
  - Image format handling
  - Memory usage optimization
  - Image processing performance

## Usage Guidelines

### Development Testing

1. **Local Development**: Use `simple_text.pdf` and `multi_page.pdf` for basic functionality testing
2. **Feature Development**: Select documents matching your specific feature (e.g., `table_document.pdf` for table extraction)
3. **Integration Testing**: Use `mixed_content.pdf` for comprehensive workflow testing

### Automated Testing

1. **Unit Tests**: Reference specific documents in test fixtures using `conftest.py`
2. **Integration Tests**: Use multiple documents to test complete workflows
3. **Performance Tests**: Use `large_document.pdf` for benchmarking and scalability testing

### API Testing

1. **Endpoint Testing**: Upload different document types to test various API endpoints
2. **Error Handling**: Use `corrupted.pdf` and `password_protected.pdf` for error scenarios
3. **Progress Tracking**: Use `large_document.pdf` to test upload progress and job status

### Frontend Testing

1. **Upload Testing**: Test drag-and-drop and file selection with various document types
2. **Preview Testing**: Use documents with different content types for viewer testing
3. **Workflow Testing**: Use specialized documents for operation-specific testing

## File Generation

Test documents are generated using the `generate_test_pdfs.py` script:

```bash
# Generate all test documents
python generate_test_pdfs.py --output-dir ./test_documents

# Generate specific document types
python generate_test_pdfs.py --document-type simple
python generate_test_pdfs.py --document-type table
python generate_test_pdfs.py --document-type large
```

### Generation Options

- `--document-type`: Choose specific document types to generate
- `--output-dir`: Specify output directory (default: `./test_documents`)

Available document types:
- `all`: Generate all test documents (default)
- `simple`: Basic text document
- `multi-page`: Multi-page document
- `table`: Table-heavy document  
- `image`: Image-heavy document
- `large`: Large performance test document
- `corrupted`: Corrupted PDF for error testing
- `protected`: Password-protected document
- `mixed`: Mixed content document

## Security Considerations

### Test Data Privacy

- All test documents contain **synthetic/fake data only**
- No real personal information (PII) is included
- Email addresses use example.com and test domains
- Phone numbers use reserved testing ranges (555-xxxx)
- SSNs use invalid ranges for testing (000-xx-xxxx, etc.)

### Password Information

- Password-protected documents use the test password: `testpass123`
- This password is documented here for testing purposes only
- Never use this password for real documents or systems

### Data Cleanup

- Test documents should be cleaned up after test execution
- Temporary files are automatically removed by generation scripts
- Session-specific test data should be isolated and cleaned up

## Integration with Test Framework

### Backend Testing (Python/Django)

```python
# Example usage in pytest
from test_documents import get_test_document

def test_pdf_processing():
    simple_pdf = get_test_document('simple_text.pdf')
    # Use in your tests...
```

### Frontend Testing (Jest/React)

```typescript
// Example usage in Jest tests
import { createMockFile } from '../test-utils';

test('file upload', () => {
  const testFile = createMockFile('simple_text.pdf');
  // Use in your tests...
});
```

## Performance Benchmarks

### Expected Processing Times

| Document | Size | Pages | Text Extraction | Table Extraction | Image Extraction |
|----------|------|-------|----------------|------------------|------------------|
| simple_text.pdf | ~10 KB | 1 | <1s | N/A | N/A |
| multi_page.pdf | ~25 KB | 5 | <2s | N/A | N/A |
| table_document.pdf | ~30 KB | 1 | <1s | <3s | N/A |
| image_document.pdf | ~50 KB | 1 | <1s | N/A | <5s |
| mixed_content.pdf | ~40 KB | 1 | <1s | <3s | <5s |
| large_document.pdf | ~3 MB | 100 | <30s | <60s | <120s |

*Benchmarks are approximate and may vary based on system specifications*

### Memory Usage Guidelines

- Small documents (<100 KB): <50 MB peak memory
- Medium documents (100 KB - 1 MB): <100 MB peak memory  
- Large documents (>1 MB): <500 MB peak memory
- Concurrent processing: Memory usage scales linearly with number of operations

## Troubleshooting

### Common Issues

1. **Generation Script Fails**
   - Ensure all dependencies are installed: `pip install reportlab pillow PyPDF2`
   - Check write permissions in output directory
   - Verify Python version compatibility (3.8+)

2. **Corrupted Document Testing**
   - `corrupted.pdf` is intentionally malformed
   - Expected to fail parsing - this is correct behavior
   - Use for testing error handling, not successful processing

3. **Password-Protected Document**
   - Always use password `testpass123` for protected document testing
   - Test both correct and incorrect password scenarios
   - Verify error messages for authentication failures

4. **Large Document Performance**
   - `large_document.pdf` is designed for performance testing
   - May take significant time to process - this is expected
   - Use timeout settings appropriate for your testing environment

### Validation

To validate test documents after generation:

```bash
# Check document integrity (except corrupted.pdf)
python -c "
import PyPDF2
import glob
import os

for pdf_file in glob.glob('*.pdf'):
    if 'corrupted' in pdf_file:
        continue
    try:
        with open(pdf_file, 'rb') as f:
            reader = PyPDF2.PdfReader(f)
            print(f'{pdf_file}: {len(reader.pages)} pages - OK')
    except Exception as e:
        print(f'{pdf_file}: ERROR - {e}')
"
```

## Maintenance

### Regular Updates

- Regenerate test documents monthly or when requirements change
- Update synthetic data to reflect current testing needs
- Validate document integrity after regeneration
- Update documentation when new document types are added

### Version Control

- Test documents are generated files and should not be committed to version control
- Only the generation script (`generate_test_pdfs.py`) should be version controlled
- Include test document generation in CI/CD pipeline setup steps
- Use `.gitignore` to exclude generated PDF files

### Dependencies

The test document generation requires:
- `reportlab`: PDF generation and layout
- `pillow`: Image processing and generation
- `PyPDF2`: PDF manipulation and encryption
- `numpy`: Numerical operations for image generation

Install all dependencies:
```bash
pip install reportlab pillow PyPDF2 numpy
```

## Support

For issues with test documents or generation:

1. Check this README for troubleshooting steps
2. Verify all dependencies are correctly installed
3. Ensure Python environment compatibility
4. Review generation script logs for specific errors
5. Validate file permissions in output directory

The test document infrastructure is designed to be comprehensive yet maintainable, providing realistic testing scenarios while ensuring privacy and security compliance.