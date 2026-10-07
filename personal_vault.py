# personal_vault.py
"""
PersonalVault 核心模块 v3
新增：恢复密钥 / 双空间 / 隐写 / 健康检查 / 坏块跳过
"""
import os
import json
import hmac
import struct
import secrets
import hashlib
import tempfile
import tarfile
import shutil
import re
import string
from datetime import datetime, timezone
from typing import Optional, List, Callable, Tuple

from cryptography.hazmat.primitives import hashes
from cryptography.hazmat.primitives.kdf.pbkdf2 import PBKDF2HMAC
from cryptography.hazmat.primitives.ciphers import Cipher, algorithms, modes
from cryptography.hazmat.backends import default_backend

MAGIC = b"PVLT"
VERSION = 3
PBKDF2_ITERATIONS = 200_000
SALT_SIZE = 32
KEY_SIZE = 32
IV_SIZE = 12
TAG_SIZE = 16
HMAC_SIZE = 32
CHUNK_SIZE = 8 * 1024 * 1024


class PasswordError(Exception): pass
class IntegrityError(Exception): pass
class ExpiredError(Exception): pass
class RecoveryKeyError(Exception): pass


# ==================== 密钥派生 ====================
def derive_master_key(password: str, salt: bytes,
                      iterations: int = PBKDF2_ITERATIONS) -> bytes:
    kdf = PBKDF2HMAC(algorithm=hashes.SHA256(), length=KEY_SIZE, salt=salt,
                     iterations=iterations, backend=default_backend())
    return kdf.derive(password.encode('utf-8'))


def generate_recovery_key() -> str:
    raw = secrets.token_hex(32)
    return '-'.join(raw[i:i+8] for i in range(0, 64, 8))


def _recovery_key_bytes(recovery_key: str) -> bytes:
    s = recovery_key.strip().replace('-', '').replace(' ', '').lower()
    if len(s) != 64:
        raise RecoveryKeyError("恢复密钥格式错误（应为 64 个十六进制字符）")
    try:
        return bytes.fromhex(s)
    except ValueError:
        raise RecoveryKeyError("恢复密钥包含无效字符")


def _wrap_key(file_key: bytes, master_key: bytes) -> bytes:
    iv = secrets.token_bytes(IV_SIZE)
    c = Cipher(algorithms.AES(master_key), modes.GCM(iv), backend=default_backend())
    e = c.encryptor()
    ct = e.update(file_key) + e.finalize()
    return iv + e.tag + ct


def _unwrap_key(wrapped: bytes, master_key: bytes) -> bytes:
    iv = wrapped[:IV_SIZE]
    tag = wrapped[IV_SIZE:IV_SIZE+TAG_SIZE]
    ct = wrapped[IV_SIZE+TAG_SIZE:]
    c = Cipher(algorithms.AES(master_key), modes.GCM(iv, tag), backend=default_backend())
    d = c.decryptor()
    return d.update(ct) + d.finalize()


def _encrypt_chunk(fk: bytes, block: bytes) -> bytes:
    iv = secrets.token_bytes(IV_SIZE)
    c = Cipher(algorithms.AES(fk), modes.GCM(iv), backend=default_backend())
    e = c.encryptor()
    ct = e.update(block) + e.finalize()
    return struct.pack('<I', len(ct)) + iv + e.tag + ct


def _decrypt_chunk(fk: bytes, iv: bytes, tag: bytes, ct: bytes) -> bytes:
    c = Cipher(algorithms.AES(fk), modes.GCM(iv, tag), backend=default_backend())
    d = c.decryptor()
    return d.update(ct) + d.finalize()


def _encrypted_size(plain_size: int) -> int:
    n = (plain_size + CHUNK_SIZE - 1) // CHUNK_SIZE if plain_size > 0 else 0
    return n * (4 + IV_SIZE + TAG_SIZE) + plain_size + 4


class TaskContext:
    def __init__(self, password: str):
        if not password or not password.strip():
            raise ValueError("密码不能为空")
        self.password = password
        self.salt = secrets.token_bytes(SALT_SIZE)
        self.iterations = PBKDF2_ITERATIONS
        self._mk = None
        self._cache = {}

    @property
    def master_key(self):
        if self._mk is None:
            self._mk = derive_master_key(self.password, self.salt, self.iterations)
        return self._mk

    def get_master_key_for(self, salt: bytes, iterations: int) -> bytes:
        if salt == self.salt and iterations == self.iterations:
            return self.master_key
        k = (salt.hex(), iterations)
        if k not in self._cache:
            self._cache[k] = derive_master_key(self.password, salt, iterations)
        return self._cache[k]


# ==================== 工具 ====================
def hash_file(filepath: str) -> str:
    sha = hashlib.sha256()
    with open(filepath, 'rb') as f:
        for chunk in iter(lambda: f.read(65536), b''):
            sha.update(chunk)
    return sha.hexdigest()


def secure_delete(filepath: str, passes: int = 3):
    try:
        length = os.path.getsize(filepath)
        with open(filepath, 'r+b') as f:
            for _ in range(passes):
                f.seek(0); f.write(secrets.token_bytes(length))
                f.flush(); os.fsync(f.fileno())
        os.remove(filepath)
    except Exception:
        pass


# ==================== 加密 ====================
def encrypt_file(ctx: TaskContext, src_path: str, dst_path: str,
                 remove_original: bool = False,
                 expiry: Optional[datetime] = None,
                 recovery_key: Optional[str] = None,
                 hint: Optional[str] = None,
                 progress_callback: Optional[Callable] = None) -> str:
    if not os.path.isfile(src_path):
        raise FileNotFoundError(f"文件不存在: {src_path}")

    file_key = secrets.token_bytes(KEY_SIZE)
    wrapped_fk = _wrap_key(file_key, ctx.master_key)

    recovery_wrapped = None
    if recovery_key:
        rk = _recovery_key_bytes(recovery_key)
        recovery_wrapped = _wrap_key(file_key, rk)

    file_hash = hash_file(src_path)
    size = os.path.getsize(src_path)

    header = {
        "version": VERSION,
        "filehash": file_hash,
        "filename": os.path.basename(src_path),
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "kdf_salt": ctx.salt.hex(),
        "kdf_iter": ctx.iterations,
        "wrapped_fk": wrapped_fk.hex(),
        "recovery_wrapped_fk": recovery_wrapped.hex() if recovery_wrapped else None,
        "hint": hint,
        "size": size,
        "expiry": expiry.astimezone(timezone.utc).isoformat() if expiry else None,
    }
    header_json = json.dumps(header, separators=(',', ':'), ensure_ascii=False).encode('utf-8')
    header_hmac = hmac.new(ctx.master_key, header_json, hashlib.sha256).digest()

    tmp = dst_path + f".tmp.{secrets.token_hex(4)}"
    try:
        with open(tmp, 'wb') as fout:
            fout.write(MAGIC)
            fout.write(struct.pack('<I', VERSION))
            fout.write(struct.pack('<I', len(header_json)))
            fout.write(header_hmac)
            fout.write(header_json)

            processed = 0
            with open(src_path, 'rb') as fin:
                while True:
                    block = fin.read(CHUNK_SIZE)
                    if not block: break
                    fout.write(_encrypt_chunk(file_key, block))
                    processed += len(block)
                    if progress_callback:
                        progress_callback(processed, size)
            fout.write(struct.pack('<I', 0))
        os.replace(tmp, dst_path)
    finally:
        if os.path.exists(tmp):
            try: os.remove(tmp)
            except: pass

    if remove_original:
        secure_delete(src_path)
    return dst_path


# ==================== 读取头部 ====================
def read_header(enc_path: str) -> dict:
    with open(enc_path, 'rb') as f:
        magic = f.read(4)
        if magic != MAGIC:
            raise ValueError("不是有效的加密文件")
        vb = f.read(4)
        if len(vb) < 4: raise ValueError("文件损坏")
        version = struct.unpack('<I', vb)[0]
        lb = f.read(4)
        if len(lb) < 4: raise ValueError("文件损坏")
        header_len = struct.unpack('<I', lb)[0]
        header_hmac = f.read(HMAC_SIZE)
        header_json = f.read(header_len)
        if len(header_json) < header_len:
            raise ValueError("头部不完整")

    data_offset = 4 + 4 + 4 + HMAC_SIZE + header_len
    header = json.loads(header_json.decode('utf-8'))
    return {"version": version, "header": header, "header_hmac": header_hmac,
            "header_json": header_json, "data_offset": data_offset}


def check_password(enc_path: str, password: str) -> bool:
    try:
        info = read_header(enc_path)
        h = info["header"]
        salt = bytes.fromhex(h["kdf_salt"])
        iters = int(h["kdf_iter"])
        mk = derive_master_key(password, salt, iters)
        expected = hmac.new(mk, info["header_json"], hashlib.sha256).digest()
        return hmac.compare_digest(expected, info["header_hmac"])
    except Exception:
        return False


# ==================== 解密 ====================
def decrypt_file(ctx: TaskContext, enc_path: str, out_path: str,
                 check_expiry: bool = True,
                 use_recovery_key: Optional[str] = None,
                 skip_bad_chunks: bool = False,
                 progress_callback: Optional[Callable] = None) -> dict:
    info = read_header(enc_path)
    header = info["header"]
    header_json = info["header_json"]
    header_hmac = info["header_hmac"]

    if header.get("version", 1) > VERSION:
        raise ValueError(f"文件由更新版本创建 (v{header['version']})")

    if use_recovery_key:
        rk = _recovery_key_bytes(use_recovery_key)
        wrapped_hex = header.get("recovery_wrapped_fk")
        if not wrapped_hex:
            raise RecoveryKeyError("此文件未设置恢复密钥")
        try:
            file_key = _unwrap_key(bytes.fromhex(wrapped_hex), rk)
        except Exception:
            raise RecoveryKeyError("恢复密钥错误")
    else:
        salt = bytes.fromhex(header["kdf_salt"])
        iters = int(header["kdf_iter"])
        mk = ctx.get_master_key_for(salt, iters)
        expected = hmac.new(mk, header_json, hashlib.sha256).digest()
        if not hmac.compare_digest(expected, header_hmac):
            raise PasswordError("密码错误")
        try:
            file_key = _unwrap_key(bytes.fromhex(header["wrapped_fk"]), mk)
        except Exception:
            raise PasswordError("密码错误")

    if check_expiry and header.get("expiry"):
        try:
            expiry = datetime.fromisoformat(header["expiry"])
            if datetime.now(timezone.utc) > expiry:
                local = expiry.astimezone().strftime('%Y-%m-%d %H:%M')
                raise ExpiredError(f"文件已于 {local} 过期")
        except ExpiredError: raise
        except Exception: pass

    size = header.get("size", 0)
    tmp = out_path + f".tmp.{secrets.token_hex(4)}"
    bad_chunks = 0
    recovered_bytes = 0

    try:
        with open(enc_path, 'rb') as fin:
            fin.seek(info["data_offset"])
            with open(tmp, 'wb') as fout:
                while True:
                    lb = fin.read(4)
                    if len(lb) < 4:
                        raise IntegrityError("文件不完整")
                    chunk_len = struct.unpack('<I', lb)[0]
                    if chunk_len == 0: break
                    iv = fin.read(IV_SIZE)
                    tag = fin.read(TAG_SIZE)
                    ct = fin.read(chunk_len)
                    if len(iv) < IV_SIZE or len(tag) < TAG_SIZE or len(ct) < chunk_len:
                        raise IntegrityError("分块数据不完整")
                    try:
                        block = _decrypt_chunk(file_key, iv, tag, ct)
                    except Exception:
                        if skip_bad_chunks:
                            bad_chunks += 1
                            recovered_bytes += len(ct)
                            fout.write(b'\x00' * len(ct))
                            continue
                        raise IntegrityError("分块认证失败")
                    fout.write(block)
                    if progress_callback:
                        progress_callback(fout.tell(), size)

        if bad_chunks == 0:
            if hash_file(tmp) != header["filehash"]:
                raise IntegrityError("完整性校验失败")
        os.replace(tmp, out_path)
    finally:
        if os.path.exists(tmp):
            try: os.remove(tmp)
            except: pass

    return {"output": out_path, "bad_chunks": bad_chunks,
            "recovered_bytes": recovered_bytes}


# ==================== 健康检查 ====================
def health_check(enc_path: str, password: Optional[str] = None,
                 full: bool = False) -> dict:
    result = {"path": enc_path, "valid_header": False, "valid_hmac": None,
              "valid_content": None, "bad_chunks": None, "total_chunks": None,
              "filename": None, "size": None, "expiry": None, "error": None}
    try:
        info = read_header(enc_path)
        result["valid_header"] = True
        h = info["header"]
        result["filename"] = h.get("filename")
        result["size"] = h.get("size")
        result["expiry"] = h.get("expiry")
        result["is_dual"] = h.get("dual", False)

        if not password:
            return result

        if h.get("dual"):
            # 双空间：尝试 real 或 fake
            for label in ["real", "fake"]:
                s = h.get(label, {})
                try:
                    salt = bytes.fromhex(s["kdf_salt"])
                    iters = int(s["kdf_iter"])
                    mk = derive_master_key(password, salt, iters)
                    _unwrap_key(bytes.fromhex(s["wrapped_fk"]), mk)
                    result["valid_hmac"] = True
                    result["space"] = label
                    return result
                except Exception:
                    continue
            result["valid_hmac"] = False
            result["error"] = "密码错误"
            return result

        salt = bytes.fromhex(h["kdf_salt"])
        iters = int(h["kdf_iter"])
        mk = derive_master_key(password, salt, iters)
        expected = hmac.new(mk, info["header_json"], hashlib.sha256).digest()
        result["valid_hmac"] = hmac.compare_digest(expected, info["header_hmac"])
        if not result["valid_hmac"]:
            result["error"] = "密码错误"
            return result

        if full:
            try:
                file_key = _unwrap_key(bytes.fromhex(h["wrapped_fk"]), mk)
            except Exception:
                result["error"] = "无法解包文件密钥"
                return result

            bad = 0; total = 0
            with open(enc_path, 'rb') as fin:
                fin.seek(info["data_offset"])
                while True:
                    lb = fin.read(4)
                    if len(lb) < 4: break
                    cl = struct.unpack('<I', lb)[0]
                    if cl == 0: break
                    iv = fin.read(IV_SIZE); tag = fin.read(TAG_SIZE); ct = fin.read(cl)
                    total += 1
                    try:
                        _decrypt_chunk(file_key, iv, tag, ct)
                    except Exception:
                        bad += 1
            result["valid_content"] = (bad == 0)
            result["bad_chunks"] = bad
            result["total_chunks"] = total
    except Exception as e:
        result["error"] = str(e)
    return result


# ==================== 文件夹 ====================
def encrypt_folder(ctx, folder_path, vault_path, expiry=None,
                   recovery_key=None, progress_callback=None):
    if not os.path.isdir(folder_path):
        raise NotADirectoryError(f"不是有效目录: {folder_path}")
    with tempfile.NamedTemporaryFile(suffix='.tar.gz', delete=False) as tmp:
        tar_path = tmp.name
    try:
        with tarfile.open(tar_path, 'w:gz') as tar:
            tar.add(folder_path, arcname=os.path.basename(folder_path.rstrip(os.sep + '/')))
        encrypt_file(ctx, tar_path, vault_path, remove_original=True,
                     expiry=expiry, recovery_key=recovery_key,
                     progress_callback=progress_callback)
        return vault_path
    finally:
        if os.path.exists(tar_path):
            try: os.remove(tar_path)
            except: pass


def decrypt_folder(ctx, vault_path, output_dir, progress_callback=None):
    with tempfile.NamedTemporaryFile(suffix='.tar.gz', delete=False) as tmp:
        tmp.close(); tar_path = tmp.name
    try:
        decrypt_file(ctx, vault_path, tar_path, progress_callback=progress_callback)
        with tarfile.open(tar_path, 'r:gz') as tar:
            tar.extractall(output_dir)
        return output_dir
    finally:
        if os.path.exists(tar_path):
            try: os.remove(tar_path)
            except: pass


# ==================== 双空间 ====================
def encrypt_dualspace(real_file: str, fake_file: str,
                      real_pwd: str, fake_pwd: str,
                      output_path: str,
                      expiry: Optional[datetime] = None) -> str:
    if not os.path.isfile(real_file): raise FileNotFoundError(real_file)
    if not os.path.isfile(fake_file): raise FileNotFoundError(fake_file)

    real_salt = secrets.token_bytes(SALT_SIZE)
    real_mk = derive_master_key(real_pwd, real_salt)
    real_fk = secrets.token_bytes(KEY_SIZE)

    fake_salt = secrets.token_bytes(SALT_SIZE)
    fake_mk = derive_master_key(fake_pwd, fake_salt)
    fake_fk = secrets.token_bytes(KEY_SIZE)

    real_hash = hash_file(real_file)
    fake_hash = hash_file(fake_file)
    real_size = os.path.getsize(real_file)
    fake_size = os.path.getsize(fake_file)
    real_enc_size = _encrypted_size(real_size)

    header = {
        "version": VERSION,
        "dual": True,
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "expiry": expiry.astimezone(timezone.utc).isoformat() if expiry else None,
        "real": {
            "filename": os.path.basename(real_file),
            "size": real_size, "hash": real_hash,
            "kdf_salt": real_salt.hex(), "kdf_iter": PBKDF2_ITERATIONS,
            "wrapped_fk": _wrap_key(real_fk, real_mk).hex(),
        },
        "fake": {
            "filename": os.path.basename(fake_file),
            "size": fake_size, "hash": fake_hash,
            "kdf_salt": fake_salt.hex(), "kdf_iter": PBKDF2_ITERATIONS,
            "wrapped_fk": _wrap_key(fake_fk, fake_mk).hex(),
        },
    }
    header_json = json.dumps(header, separators=(',', ':'), ensure_ascii=False).encode('utf-8')

    tmp = output_path + f".tmp.{secrets.token_hex(4)}"
    try:
        with open(tmp, 'wb') as fout:
            fout.write(MAGIC)
            fout.write(struct.pack('<I', VERSION))
            fout.write(struct.pack('<I', len(header_json)))
            fout.write(b'\x00' * HMAC_SIZE)
            fout.write(header_json)
            fout.write(struct.pack('<Q', real_enc_size))

            with open(real_file, 'rb') as fin:
                while True:
                    b = fin.read(CHUNK_SIZE)
                    if not b: break
                    fout.write(_encrypt_chunk(real_fk, b))
            fout.write(struct.pack('<I', 0))

            with open(fake_file, 'rb') as fin:
                while True:
                    b = fin.read(CHUNK_SIZE)
                    if not b: break
                    fout.write(_encrypt_chunk(fake_fk, b))
            fout.write(struct.pack('<I', 0))

        os.replace(tmp, output_path)
    finally:
        if os.path.exists(tmp):
            try: os.remove(tmp)
            except: pass
    return output_path


def decrypt_dualspace(pwd: str, enc_path: str, out_dir: str) -> Tuple[str, str]:
    info = read_header(enc_path)
    header = info["header"]
    if not header.get("dual"):
        raise ValueError("不是双空间文件")
    os.makedirs(out_dir, exist_ok=True)

    space_type = None; space = None; file_key = None
    for label in ["real", "fake"]:
        s = header[label]
        try:
            salt = bytes.fromhex(s["kdf_salt"])
            iters = int(s["kdf_iter"])
            mk = derive_master_key(pwd, salt, iters)
            fk = _unwrap_key(bytes.fromhex(s["wrapped_fk"]), mk)
            space_type, space, file_key = label, s, fk
            break
        except Exception:
            continue

    if space is None:
        raise PasswordError("密码错误")

    with open(enc_path, 'rb') as f:
        f.seek(info["data_offset"])
        real_len_b = f.read(8)
        if len(real_len_b) < 8: raise IntegrityError("头部不完整")
        real_len = struct.unpack('<Q', real_len_b)[0]
        real_start = info["data_offset"] + 8
        fake_start = real_start + real_len

    data_offset = real_start if space_type == "real" else fake_start
    out_path = os.path.join(out_dir, space["filename"])
    tmp = out_path + f".tmp.{secrets.token_hex(4)}"
    try:
        with open(enc_path, 'rb') as fin:
            fin.seek(data_offset)
            with open(tmp, 'wb') as fout:
                while True:
                    lb = fin.read(4)
                    if len(lb) < 4: break
                    cl = struct.unpack('<I', lb)[0]
                    if cl == 0: break
                    iv = fin.read(IV_SIZE); tag = fin.read(TAG_SIZE); ct = fin.read(cl)
                    if len(iv) < IV_SIZE or len(tag) < TAG_SIZE or len(ct) < cl:
                        raise IntegrityError("分块不完整")
                    try:
                        block = _decrypt_chunk(file_key, iv, tag, ct)
                    except Exception:
                        raise IntegrityError("分块认证失败")
                    fout.write(block)
        if hash_file(tmp) != space["hash"]:
            raise IntegrityError("完整性校验失败")
        os.replace(tmp, out_path)
    finally:
        if os.path.exists(tmp):
            try: os.remove(tmp)
            except: pass
    return space_type, out_path


# ==================== 隐写术 ====================
def steganography_hide(enc_path: str, carrier_image: str, output_image: str) -> str:
    try:
        from stegano import lsb
    except ImportError:
        raise ImportError("需要安装 stegano: pip install stegano")
    with open(enc_path, 'rb') as f:
        data = f.read().hex()
    secret = lsb.hide(carrier_image, data)
    secret.save(output_image)
    return output_image


def steganography_reveal(stego_image: str, output_path: str) -> str:
    try:
        from stegano import lsb
    except ImportError:
        raise ImportError("需要安装 stegano: pip install stegano")
    data = lsb.reveal(stego_image)
    if data is None:
        raise ValueError("图片中没有隐写数据")
    with open(output_path, 'wb') as f:
        f.write(bytes.fromhex(data))
    return output_path


# ==================== 批量 ====================
def batch_encrypt(ctx, file_list, remove_original=False, expiry=None,
                  recovery_key=None, progress_callback=None):
    results = []
    for i, fp in enumerate(file_list):
        try:
            dst = fp + ".enc"
            encrypt_file(ctx, fp, dst, remove_original=remove_original,
                         expiry=expiry, recovery_key=recovery_key)
            results.append({"original": fp, "encrypted": dst, "status": "success"})
        except Exception as e:
            results.append({"original": fp, "status": "error", "reason": str(e)})
        if progress_callback: progress_callback(i+1, len(file_list))
    return results


def batch_decrypt(ctx, file_list, output_dir=None, skip_bad_chunks=False,
                  progress_callback=None):
    results = []
    for i, fp in enumerate(file_list):
        try:
            info = read_header(fp)
            h = info["header"]
            if h.get("dual"):
                space, out = decrypt_dualspace(ctx.password, fp, output_dir or os.path.dirname(fp))
                results.append({"original": fp, "decrypted": out,
                                "space": space, "bad_chunks": 0, "status": "success"})
            else:
                filename = h.get("filename", os.path.basename(fp) + ".dec")
                out_dir = output_dir or os.path.dirname(fp)
                out_path = os.path.join(out_dir, filename)
                r = decrypt_file(ctx, fp, out_path, skip_bad_chunks=skip_bad_chunks)
                results.append({"original": fp, "decrypted": r["output"],
                                "bad_chunks": r["bad_chunks"], "status": "success"})
        except PasswordError:
            results.append({"original": fp, "status": "error", "reason": "密码错误"})
        except ExpiredError as e:
            results.append({"original": fp, "status": "error", "reason": str(e)})
        except Exception as e:
            results.append({"original": fp, "status": "error", "reason": str(e)})
        if progress_callback: progress_callback(i+1, len(file_list))
    return results


# ==================== 密码工具 ====================
def generate_strong_password(length: int = 16) -> str:
    chars = string.ascii_letters + string.digits + "!@#$%^&*()-_=+"
    while True:
        pwd = ''.join(secrets.choice(chars) for _ in range(length))
        if (re.search(r'[a-z]', pwd) and re.search(r'[A-Z]', pwd)
                and re.search(r'\d', pwd) and re.search(r'[^A-Za-z0-9]', pwd)):
            return pwd


def password_strength(password: str) -> Tuple[int, str]:
    if not password: return (0, "无")
    score = 0
    if len(password) >= 8: score += 1
    if len(password) >= 12: score += 1
    if re.search(r'[A-Z]', password): score += 1
    if re.search(r'[a-z]', password): score += 1
    if re.search(r'\d', password): score += 1
    if re.search(r'[^A-Za-z0-9]', password): score += 1
    labels = ["极弱", "极弱", "弱", "中", "中", "强", "极强"]
    return (score, labels[score])