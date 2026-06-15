f = open(r'd:\QODER\data\videoGen_cases.py', 'rb')
data = f.read()
f.close()

idx = data.find(b'add("NAVBAR.LOGO"')
chunk = data[idx:idx+300]
print(f"First add call at byte {idx}:")
print(chunk[:300])
print()
print("Hex around the issue:")
# Find the steps string
steps_start = chunk.find(b'"1. Click')
if steps_start >= 0:
    print(f"  Steps area (hex): {chunk[steps_start:steps_start+100].hex(' ')}")
    # Check for 0x0A (LF) vs 0x5C 0x6E (\n)
    for i, b in enumerate(chunk[steps_start:steps_start+100]):
        if b == 0x0A:
            print(f"  REAL NEWLINE (0x0A) at offset {steps_start + i}")
        elif b == 0x5C and i+1 < 100 and chunk[steps_start+i+1] == 0x6E:
            print(f"  ESCAPE SEQUENCE \\n (0x5C 0x6E) at offset {steps_start + i}")
