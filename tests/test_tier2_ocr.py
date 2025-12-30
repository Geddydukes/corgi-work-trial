#!/usr/bin/env python3
"""Test Tier 2 OCR (Tesseract) on a downloaded file."""

import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))

from document_service.ocr.service import OCRService
from shared import config

def main():
    test_file = Path("/Users/geddydukes/Downloads/Community Vision Grant confirmation letter 2022.pdf")
    
    if not test_file.exists():
        print(f"❌ Test file not found: {test_file}")
        return
    
    print(f"📄 Testing Tier 2 OCR on: {test_file.name}")
    print(f"   Full path: {test_file}")
    print()
    
    print("🔧 Configuration:")
    print(f"   OCR_TIER2_ENABLED: {config.Config.OCR_TIER2_ENABLED}")
    print(f"   TESSERACT_CMD: {config.Config.TESSERACT_CMD or 'Not set (using default)'}")
    print(f"   TESSDATA_PREFIX: {config.Config.TESSDATA_PREFIX or 'Not set (using default)'}")
    print()
    
    ocr_service = OCRService()
    
    print("🔍 Tesseract availability check:")
    print(f"   Tesseract available: {ocr_service._tesseract_available}")
    print()
    
    if not config.Config.OCR_TIER2_ENABLED:
        print("⚠️  OCR_TIER2_ENABLED is False. Set OCR_TIER2_ENABLED=true to test Tier 2.")
        return
    
    if not ocr_service._tesseract_available:
        print("⚠️  Tesseract is not available. Please install Tesseract:")
        print("   macOS: brew install tesseract")
        print("   Linux: apt-get install tesseract-ocr tesseract-ocr-eng")
        print()
        print("   Or set TESSERACT_CMD and TESSDATA_PREFIX environment variables if using custom paths.")
        return
    
    print("✅ Tier 2 OCR is enabled and Tesseract is available!")
    print()
    print("🚀 Running Tier 2 OCR extraction...")
    print()
    
    text, confidence, tier, time_ms, cost = ocr_service._extract_tier2_tesseract(test_file)
    
    print("📊 Results:")
    print(f"   Tier used: {tier}")
    print(f"   Confidence: {confidence:.2f}%")
    print(f"   Processing time: {time_ms}ms")
    print(f"   Cost: ${cost:.6f}")
    print(f"   Text length: {len(text) if text else 0} characters")
    print()
    
    if text:
        preview = text[:500] if len(text) > 500 else text
        print("📝 Extracted text preview:")
        print("-" * 80)
        print(preview)
        if len(text) > 500:
            print(f"... ({len(text) - 500} more characters)")
        print("-" * 80)
        print()
        print("✅ Tier 2 OCR test completed successfully!")
    else:
        print("❌ No text extracted. Check logs for errors.")
    
if __name__ == "__main__":
    main()

