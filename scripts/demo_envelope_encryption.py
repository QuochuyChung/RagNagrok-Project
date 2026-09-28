import os
from cryptography.hazmat.primitives.ciphers.aead import AESGCM
from app.core.encryption import generate_dek, wrap_dek, unwrap_dek

def run_demo():
    print("=== DEMO LỒNG MÃ HÓA (ENVELOPE ENCRYPTION DEK - KEK) ===")
    
    # 1. Giả lập dữ liệu chunk thô
    raw_chunk = "Chính sách nghỉ phép: Nhân viên được hưởng 100% lương..."
    print(f"\n[1] Dữ liệu Chunk gốc (Plaintext): {raw_chunk}")

    # 2. Tạo và Wrap DEK cho Tenant
    dek = generate_dek()
    wrapped_dek = wrap_dek(dek)
    print(f"\n[2] Tạo DEK ngẫu nhiên (32 bytes)")
    print(f"    DEK sau khi mã hóa bằng KEK (lưu DB): {wrapped_dek.hex()[:40]}... [binary bytes]")

    # 3. Dùng DEK Plaintext mã hóa dữ liệu Chunk
    aesgcm_dek = AESGCM(dek)
    nonce = os.urandom(12)
    encrypted_content = nonce + aesgcm_dek.encrypt(nonce, raw_chunk.encode(), None)
    print(f"\n[3] Mã hóa Content bằng DEK (Ghi xuống DB):")
    print(f"    Encrypted Content: {encrypted_content.hex()[:50]}... [Rác Binary]")

    # 4. Giả lập Luồng Đọc (Retrieval): Lấy Encrypted DEK -> Giải mã qua KEK -> Giải mã Content
    unwrapped_dek = unwrap_dek(wrapped_dek)
    aesgcm_unwrapped = AESGCM(unwrapped_dek)
    
    retrieved_nonce = encrypted_content[:12]
    ciphertext = encrypted_content[12:]
    decrypted_bytes = aesgcm_unwrapped.decrypt(retrieved_nonce, ciphertext, None)
    decrypted_text = decrypted_bytes.decode('utf-8')
    
    print(f"\n[4] Giải mã ngược lại tại Backend:")
    print(f"    Gửi Wrapped DEK lên KEK giải mã -> Thu được DEK gốc thành công.")
    print(f"    Dùng DEK giải mã Encrypted Content -> Kết quả: '{decrypted_text}'")

    # 5. Demo tính năng Chống Truy Cập / Sai KEK
    print("\n[5] Test Bảo Mật (Negative Test):")
    try:
        # Giả lập sai KEK bằng cách truyền binary rác
        unwrap_dek(b"invalid_wrapped_dek_bytes_1234567890")
    except Exception as e:
        print(f"    [SUCCESS] Hệ thống chặn thành công: {e}")

if __name__ == "__main__":
    run_demo()