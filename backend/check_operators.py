import zlib
import re

def dump_pdf_stream_operators(path):
    print("=== OPERATORS IN", path, "===")
    with open(path, "rb") as f:
        raw = f.read()

    for i, m in enumerate(re.finditer(b"stream\r?\n(.*?)\r?\nendstream", raw, re.DOTALL)):
        try:
            decomp = zlib.decompress(m.group(1))
            # look for TJ or Tj
            hex_strings = re.findall(rb'<([0-9a-fA-F]+)>\s*Tj', decomp)
            if hex_strings:
                print(f"Stream {i} has {len(hex_strings)} hex Tj strings")
                # print first few
                for h in hex_strings[:5]:
                    print("  hex:", h[:40])
            array_tj = re.findall(rb'\[(.*?)\]\s*TJ', decomp)
            if array_tj:
                print(f"Stream {i} has {len(array_tj)} array TJ blocks")
                for a in array_tj[:3]:
                    print("  array:", a[:80])
        except Exception:
            pass

dump_pdf_stream_operators("backend/media/answer_papers/6th_SS_MA.pdf")
dump_pdf_stream_operators("backend/media/question_papers/6TH_SS_QP_1.pdf")

