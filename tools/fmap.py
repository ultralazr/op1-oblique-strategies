"""Map OP1_vdk.ldr file offsets <-> load addresses."""
import sys, os
sys.path.insert(0, os.path.dirname(__file__)); import ldr
def off2addr(d, off):
    for b in ldr.blocks(d):
        if b['data_off'] <= off < b['data_off'] + b['payload']:
            return b['addr'] + off - b['data_off'], b
        if b['off'] <= off < b['data_off']:
            return None, b
    return None, None
def addr2off(d, addr):
    for b in ldr.blocks(d):
        if b['payload'] and not b['flags'] & (ldr.FILL | ldr.IGNORE | ldr.FIRST) and b['addr'] <= addr < b['addr'] + b['payload']:
            return b['data_off'] + addr - b['addr']
    return None
