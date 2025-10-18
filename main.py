"""
Entropy & BSC Simulation + Encode/Decode Tool (Tkinter) — Updated

Features:
- Load a .txt file (path entry or file dialog)
- Accepts only the 64-character alphabet:
    a-z, A-Z, digits '1'..'9', space ' ', comma ',', period '.'
  Any other character is mapped to space ' '.
- Compute PMF, show bar plot (embedded matplotlib), compute:
    - H(X) (entropy of characters)
    - D(P || U) relative entropy vs uniform over 64 symbols
- Encode characters using Huffman or Shannon-Fano (choose the more efficient;
  tie -> Shannon-Fano), save the encoded file (JSON inside a .txt).
- Fixed 6-bit-per-symbol encoding used to simulate a Binary Symmetric Channel (BSC)
  with configurable flip probability p (default 0.05) and optional seed.
- Decode the received BSC bitstring back to characters and compute:
    - joint entropy H(X,Y)
    - conditional entropy H(Y|X)
    - chain rule verification
- Compare Huffman vs Shannon-Fano (average code length and runtime)
- Save analysis results (pmf plot, pmf.csv, report.txt, bsc_received_decoded.txt) to a directory
- NEW: "Load Encoded .txt and Decode" placed in the dashboard — decoded text appears
  in the main GUI (Decoded pane) and can be saved from there (no popup).
- All UI in a single window (dashboard).

Usage:
- Save as a Python file (e.g., entropy_bsc_dashboard.py) and run with Python 3.
- Requires: tkinter, numpy, matplotlib

Author: Tailored for user's project.
"""

import os
import json
import math
import time
from collections import Counter
from heapq import heappush, heappop
import tkinter as tk
from tkinter import ttk, filedialog, messagebox
import numpy as np
import matplotlib.pyplot as plt
from matplotlib.backends.backend_tkagg import FigureCanvasTkAgg

# -----------------------
# Alphabet and helpers
# -----------------------
LOWER = [chr(i) for i in range(ord('a'), ord('z') + 1)]
UPPER = [chr(i) for i in range(ord('A'), ord('Z') + 1)]
DIGITS = [str(i) for i in range(1, 10)]  # '1'..'9'
OTHERS = [' ', ',', '.']
ALPHABET = LOWER + UPPER + DIGITS + OTHERS
ALPHABET_INDEX = {c: i for i, c in enumerate(ALPHABET)}
N_SYMBOLS = len(ALPHABET)  # expected 64

def map_char(c, fallback=' '):
    """Map char to allowed alphabet or fallback (space)."""
    return c if c in ALPHABET_INDEX else fallback

def read_and_map_file(path):
    """Read file, map characters to allowed alphabet, return list."""
    with open(path, 'r', encoding='utf-8', errors='ignore') as f:
        raw = f.read()
    return [map_char(ch) for ch in raw]

def pmf_from_list(mapped_chars):
    counts = Counter(mapped_chars)
    total = sum(counts.values())
    pmf = {c: (counts.get(c, 0) / total if total > 0 else 0.0) for c in ALPHABET}
    return counts, pmf, total

def entropy_from_pmf(pmf):
    return -sum(p * math.log2(p) for p in pmf.values() if p > 0)

def relative_entropy_to_uniform(pmf):
    U = 1.0 / N_SYMBOLS
    return sum(p * math.log2(p / U) for p in pmf.values() if p > 0)

# -----------------------
# Fixed 6-bit encoding (for BSC simulation)
# -----------------------
def mapped_chars_to_6bit_bits(mapped_chars):
    """Return bitstring of 6-bit indices for mapped_chars."""
    return ''.join(format(ALPHABET_INDEX[c], '06b') for c in mapped_chars)

def simulate_bsc_on_bitstring(bitstring, p=0.05, seed=None):
    rng = np.random.default_rng(seed)
    arr = np.array(list(bitstring), dtype='U1')
    n = len(arr)
    flips = rng.random(n) < p
    recv = np.where(flips, np.where(arr == '0', '1', '0'), arr)
    return ''.join(recv)

def bitstring_to_mapped_chars(bitstring):
    """Decode 6-bit chunks back to mapped chars (truncate remainder)."""
    n = (len(bitstring) // 6) * 6
    chars = []
    for i in range(0, n, 6):
        idx = int(bitstring[i:i+6], 2) % N_SYMBOLS
        chars.append(ALPHABET[idx])
    return chars

def joint_entropy(xs, ys):
    assert len(xs) == len(ys)
    if len(xs) == 0:
        return 0.0
    counts = Counter(zip(xs, ys))
    total = len(xs)
    return -sum((v/total) * math.log2(v/total) for v in counts.values() if v > 0)

# -----------------------
# Huffman and Shannon-Fano (compare & compression)
# -----------------------
def huffman_code(symbols, probs):
    heap = []
    counter = 0
    for s, p in zip(symbols, probs):
        heappush(heap, (p, counter, (s, None, None)))
        counter += 1
    if not heap:
        return {}
    if len(heap) == 1:
        return {heap[0][2][0]: '0'}
    while len(heap) > 1:
        p1, c1, n1 = heappop(heap)
        p2, c2, n2 = heappop(heap)
        merged = (None, n1, n2)
        heappush(heap, (p1 + p2, counter, merged))
        counter += 1
    root = heap[0][2]
    codes = {}
    def traverse(node, prefix):
        symbol, left, right = node
        if symbol is not None:
            codes[symbol] = prefix or '0'
            return
        traverse(left, prefix + '0')
        traverse(right, prefix + '1')
    traverse(root, '')
    return codes

def shannon_fano_code(symbols, probs):
    items = list(zip(symbols, probs))
    items.sort(key=lambda x: x[1], reverse=True)
    codes = {s: '' for s, _ in items}
    def recurse(subitems):
        if len(subitems) <= 1:
            return
        total = sum(p for _, p in subitems)
        acc = 0.0
        best_idx = None
        best_diff = None
        for i in range(1, len(subitems)):
            acc += subitems[i-1][1]
            diff = abs((total - acc) - acc)
            if best_diff is None or diff < best_diff:
                best_diff = diff
                best_idx = i
        left = subitems[:best_idx]
        right = subitems[best_idx:]
        for s, _ in left: codes[s] += '0'
        for s, _ in right: codes[s] += '1'
        recurse(left)
        recurse(right)
    recurse(items)
    return codes

def avg_code_length(codes, pmf):
    return sum(len(codes[s]) * pmf.get(s, 0.0) for s in codes)

def compare_and_choose_codes(pmf):
    """Return huffman/sf codes, avg lengths, runtimes and chosen algorithm."""
    symbols = ALPHABET[:]  # fixed order
    probs = [pmf[s] for s in symbols]
    t0 = time.perf_counter()
    hcodes = huffman_code(symbols, probs)
    th = time.perf_counter() - t0
    t1 = time.perf_counter()
    sfcodes = shannon_fano_code(symbols, probs)
    tsf = time.perf_counter() - t1
    Lh = avg_code_length(hcodes, pmf)
    Lsf = avg_code_length(sfcodes, pmf)
    tol = 1e-12
    if abs(Lh - Lsf) <= tol:
        chosen = 'Shannon-Fano'
    else:
        chosen = 'Huffman' if Lh < Lsf else 'Shannon-Fano'
    return {
        'huffman_codes': hcodes,
        'shannon_fano_codes': sfcodes,
        'L_huffman': Lh,
        'L_shannon_fano': Lsf,
        'time_huffman': th,
        'time_shannon_fano': tsf,
        'chosen': chosen
    }

def encode_with_codebook(mapped_chars, codebook):
    """Return bitstring by concatenating codebook[symbol] for each symbol."""
    return ''.join(codebook[s] for s in mapped_chars)

def decode_bitstring_with_codebook(bitstring, codebook):
    """Prefix decode bitstring using codebook (code->symbol). Returns list of symbols."""
    # Build trie from codebook
    trie = {}
    for sym, code in codebook.items():
        node = trie
        for bit in code:
            node = node.setdefault(bit, {})
        node['_sym'] = sym
    # Walk bits
    out = []
    node = trie
    for b in bitstring:
        if b not in node:
            # On invalid path, reset to root and try to sync
            node = trie
            # skip this bit (recovering sync could be improved)
            continue
        node = node[b]
        if '_sym' in node:
            out.append(node['_sym'])
            node = trie
    return out

# -----------------------
# GUI Application
# -----------------------
class EntropyBSCApp(tk.Tk):
    def __init__(self):
        super().__init__()
        self.title("Entropy & BSC Simulation + Encode/Decode Dashboard")
        self.geometry("1150x820")
        self.resizable(True, True)

        # State variables
        self.filepath = tk.StringVar()
        self.p_bsc = tk.DoubleVar(value=0.05)
        self.seed_text = tk.StringVar(value="random")
        self.pmfs = None
        self.counts = None
        self.total_chars = 0
        self.mapped_chars = []
        self.bsc_decoded_chars = []
        self.compress_result = None
        self.compressed_bitstring = None
        self.compressed_algo = None
        self.compressed_codebook = None
        self.results = None

        # Build UI
        self._build_top_controls()
        self._build_plot_area()
        self._build_results_area()
        self._build_decoded_area()
        self._build_bottom_controls()

    def _build_top_controls(self):
        frm = ttk.Frame(self)
        frm.pack(side=tk.TOP, fill=tk.X, padx=8, pady=6)

        ttk.Label(frm, text="Text file path:").grid(row=0, column=0, sticky='w')
        ttk.Entry(frm, textvariable=self.filepath, width=82).grid(row=0, column=1, padx=6)
        ttk.Button(frm, text="Browse", command=self.browse_file).grid(row=0, column=2, padx=4)

        ttk.Label(frm, text="BSC p (flip prob):").grid(row=1, column=0, sticky='w', pady=6)
        ttk.Entry(frm, textvariable=self.p_bsc, width=10).grid(row=1, column=1, sticky='w')

        ttk.Label(frm, text="Random seed (int) or 'random':").grid(row=2, column=0, sticky='w')
        ttk.Entry(frm, textvariable=self.seed_text, width=12).grid(row=2, column=1, sticky='w')

        ttk.Button(frm, text="Process File (PMF, Entropy, BSC)", command=self.process_file).grid(row=1, column=2, padx=6)
        ttk.Button(frm, text="Compare & Choose Compression", command=self.compare_and_show).grid(row=2, column=2, padx=6)
        ttk.Button(frm, text="Save All Results", command=self.save_results).grid(row=0, column=3, padx=8)

    def _build_plot_area(self):
        self.fig, self.ax = plt.subplots(figsize=(11, 3.6))
        self.fig.tight_layout()
        frame = ttk.Frame(self)
        frame.pack(fill=tk.BOTH, expand=False, padx=8, pady=4)
        self.canvas = FigureCanvasTkAgg(self.fig, master=frame)
        self.canvas.get_tk_widget().pack(fill=tk.BOTH, expand=True)

    def _build_results_area(self):
        frame = ttk.LabelFrame(self, text="Analysis Results")
        frame.pack(fill=tk.BOTH, expand=False, padx=8, pady=6)
        self.results_text = tk.Text(frame, height=12, wrap='word')
        self.results_text.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        scrollbar = ttk.Scrollbar(frame, orient=tk.VERTICAL, command=self.results_text.yview)
        scrollbar.pack(side=tk.RIGHT, fill=tk.Y)
        self.results_text['yscrollcommand'] = scrollbar.set

    def _build_decoded_area(self):
        frame = ttk.LabelFrame(self, text="Decoded from Encoded File (Load an encoded .txt below)")
        frame.pack(fill=tk.BOTH, expand=True, padx=8, pady=6)
        # Provide a small toolbar above decoded area
        toolbar = ttk.Frame(frame)
        toolbar.pack(fill=tk.X, padx=4, pady=3)
        ttk.Button(toolbar, text="Load Encoded .txt and Decode", command=self.load_compressed_and_decode_dashboard).pack(side=tk.LEFT, padx=4)
        ttk.Button(toolbar, text="Save Decoded Text", command=self.save_decoded_from_dashboard).pack(side=tk.LEFT, padx=4)
        # Decoded text area
        self.decoded_text_widget = tk.Text(frame, height=12, wrap='word')
        self.decoded_text_widget.pack(fill=tk.BOTH, expand=True)
        decoded_scroll = ttk.Scrollbar(frame, orient=tk.VERTICAL, command=self.decoded_text_widget.yview)
        decoded_scroll.pack(side=tk.RIGHT, fill=tk.Y)
        self.decoded_text_widget['yscrollcommand'] = decoded_scroll.set

    def _build_bottom_controls(self):
        frm = ttk.Frame(self)
        frm.pack(fill=tk.X, padx=8, pady=6)
        ttk.Button(frm, text="Save Compressed .txt (json inside)", command=self.save_compressed_file).grid(row=0, column=0, padx=6)
        ttk.Button(frm, text="Exit", command=self.quit).grid(row=0, column=5, padx=6)

    # -----------------------
    # Actions
    # -----------------------
    def browse_file(self):
        p = filedialog.askopenfilename(filetypes=[("Text Files", "*.txt"), ("All Files", "*.*")])
        if p:
            self.filepath.set(p)

    def process_file(self):
        path = self.filepath.get().strip()
        if not path or not os.path.isfile(path):
            messagebox.showerror("Error", "Please select a valid text file.")
            return
        mapped = read_and_map_file(path)
        self.mapped_chars = mapped
        counts, pmf, total = pmf_from_list(mapped)
        self.counts = counts
        self.pmfs = pmf
        self.total_chars = total

        Hx = entropy_from_pmf(pmf)
        Dkl = relative_entropy_to_uniform(pmf)

        # Fixed 6-bit encode and BSC simulation
        bits = mapped_chars_to_6bit_bits(mapped)
        seed = None
        seed_text = self.seed_text.get().strip()
        if seed_text.lower() != 'random':
            try:
                seed = int(seed_text)
            except:
                seed = None
        p = float(self.p_bsc.get())
        recv_bits = simulate_bsc_on_bitstring(bits, p=p, seed=seed)
        recv_chars = bitstring_to_mapped_chars(recv_bits)
        self.bsc_decoded_chars = recv_chars

        Hxy = joint_entropy(mapped, recv_chars)
        Hy_given_x = Hxy - Hx
        chain_diff = Hxy - (Hx + Hy_given_x)  # should be ~0

        # Save results into state
        self.results = {
            'file': path,
            'total_chars': total,
            'H_x': Hx,
            'D_PU': Dkl,
            'p_bsc': p,
            'seed': seed if seed is not None else 'random',
            'bits_length': len(bits),
            'H_xy': Hxy,
            'H_y_given_x': Hy_given_x,
            'chain_diff': chain_diff
        }

        # Update UI
        self._plot_pmf(pmf)
        self._display_results_text()

    def _plot_pmf(self, pmf):
        self.ax.clear()
        chars = ALPHABET
        probs = [pmf[c] for c in chars]
        x = range(len(chars))
        self.ax.bar(x, probs, tick_label=chars)
        self.ax.set_xlabel("Character")
        self.ax.set_ylabel("Probability")
        self.ax.set_title("PMF of characters in file")
        self.ax.set_ylim(0, max(probs) * 1.10 if probs else 1)
        self.fig.tight_layout()
        self.canvas.draw()

    def _display_results_text(self):
        r = self.results
        self.results_text.delete('1.0', tk.END)
        lines = []
        lines.append(f"File: {r.get('file')}")
        lines.append(f"Total characters processed: {r.get('total_chars')}")
        lines.append("")
        lines.append("Top character frequencies:")
        for ch, cnt in sorted(self.counts.items(), key=lambda x: x[1], reverse=True)[:16]:
            label = "'space'" if ch == ' ' else ch
            lines.append(f"  {label:7s} : {cnt} ({self.pmfs[ch]:.6f})")
        lines.append("")
        lines.append(f"H(X) = {r['H_x']:.6f} bits")
        lines.append(f"D(P || U) = {r['D_PU']:.6f} bits (uniform over {N_SYMBOLS} symbols)")
        lines.append("")
        lines.append(f"BSC settings: p={r['p_bsc']}, seed={r['seed']}, bits length={r['bits_length']}")
        lines.append("")
        lines.append(f"H(X,Y) = {r['H_xy']:.6f} bits")
        lines.append(f"H(Y|X) = {r['H_y_given_x']:.6f} bits")
        lines.append(f"Chain rule diff = {r['chain_diff']:.6e} (should be ~0)")
        lines.append("")
        lines.append("You can optionally compare compression algorithms and save/load compressed files.")
        self.results_text.insert(tk.END, '\n'.join(lines))

    def compare_and_show(self):
        if not self.pmfs:
            messagebox.showinfo("Info", "Process a file first to obtain PMF.")
            return
        comp = compare_and_choose_codes(self.pmfs)
        self.compress_result = comp
        chosen = comp['chosen']
        # Build chosen codebook and compressed bits for current mapped chars
        codebook = comp['huffman_codes'] if chosen == 'Huffman' else comp['shannon_fano_codes']
        compressed_bits = encode_with_codebook(self.mapped_chars, codebook)
        self.compressed_bitstring = compressed_bits
        self.compressed_algo = chosen
        self.compressed_codebook = codebook
        info = [
            f"Chosen: {chosen}",
            f"Avg length Huffman = {comp['L_huffman']:.6f}, time = {comp['time_huffman']:.6f}s",
            f"Avg length Shannon-Fano = {comp['L_shannon_fano']:.6f}, time = {comp['time_shannon_fano']:.6f}s",
            "",
            "Sample codes (first 12 alphabet symbols):"
        ]
        codes = comp['huffman_codes'] if chosen == 'Huffman' else comp['shannon_fano_codes']
        for s in ALPHABET[:12]:
            info.append(f"  {repr(s):6s} : {codes.get(s,'')}")
        messagebox.showinfo("Compression Comparison", "\n".join(info))

    def save_compressed_file(self):
        """Save encoded compressed data & codebook into a single .txt file (JSON inside)."""
        if not self.compressed_bitstring or not self.compressed_algo or not self.compressed_codebook:
            messagebox.showinfo("Info", "No compressed data present. Use Compare & Choose Compression first.")
            return
        out_path = filedialog.asksaveasfilename(defaultextension=".txt", filetypes=[("Text file", "*.txt")])
        if not out_path:
            return
        payload = {
            'algorithm': self.compressed_algo,
            'codebook': self.compressed_codebook,  # symbol -> code
            'encoded_data': self.compressed_bitstring,
            'metadata': {
                'source_file': os.path.basename(self.filepath.get() or ""),
                'total_symbols': self.total_chars,
                'timestamp': time.time()
            }
        }
        with open(out_path, 'w', encoding='utf-8') as f:
            json.dump(payload, f)
        messagebox.showinfo("Saved", f"Compressed file saved to:\n{out_path}")

    # -----------------------
    # NEW: Load encoded file and decode INTO DASHBOARD decoded_text_widget
    # -----------------------
    def load_compressed_and_decode_dashboard(self):
        """Load a compressed .txt (JSON inside) and decode; display decoded text in the decoded area."""
        path = filedialog.askopenfilename(filetypes=[("Text file", "*.txt"), ("All files", "*.*")])
        if not path:
            return
        try:
            with open(path, 'r', encoding='utf-8') as f:
                payload = json.load(f)
        except Exception as e:
            messagebox.showerror("Error", f"Failed to read compressed file: {e}")
            return
        if not all(k in payload for k in ('algorithm', 'codebook', 'encoded_data')):
            messagebox.showerror("Error", "Invalid compressed file format (missing fields).")
            return
        codebook = payload['codebook']
        encoded = payload['encoded_data']
        # Decode (prefix decode)
        try:
            decoded_symbols = decode_bitstring_with_codebook(encoded, codebook)
        except Exception as e:
            messagebox.showerror("Error during decode", str(e))
            return
        decoded_text = ''.join(decoded_symbols)
        # Put decoded text into the decoded_text_widget (dashboard)
        self.decoded_text_widget.delete('1.0', tk.END)
        self.decoded_text_widget.insert(tk.END, decoded_text)
        # Optionally, store a reference for saving
        self._decoded_loaded_info = {
            'source_path': path,
            'decoded_text': decoded_text,
            'algo': payload.get('algorithm'),
            'metadata': payload.get('metadata', {})
        }
        messagebox.showinfo("Decoded", f"Decoded {len(decoded_symbols)} symbols from:\n{path}")

    def save_decoded_from_dashboard(self):
        """Save the decoded text currently shown in the dashboard decoded area."""
        info = getattr(self, '_decoded_loaded_info', None)
        text_to_save = self.decoded_text_widget.get('1.0', tk.END)
        if not text_to_save.strip():
            messagebox.showinfo("Info", "No decoded text to save. Load an encoded file first.")
            return
        p = filedialog.asksaveasfilename(defaultextension=".txt", filetypes=[("Text file", "*.txt")])
        if not p:
            return
        with open(p, 'w', encoding='utf-8') as f:
            f.write(text_to_save)
        messagebox.showinfo("Saved", f"Decoded text saved to:\n{p}")

    def save_results(self):
        if not getattr(self, 'results', None):
            messagebox.showinfo("Info", "No results to save. Process a file first.")
            return
        folder = filedialog.askdirectory(title="Choose folder to save results")
        if not folder:
            return
        base = os.path.splitext(os.path.basename(self.results['file']))[0]
        outdir = os.path.join(folder, f"{base}_results")
        os.makedirs(outdir, exist_ok=True)

        # 1) PMF plot
        plot_path = os.path.join(outdir, "pmf_plot.png")
        self.fig.savefig(plot_path)

        # 2) pmf CSV
        pmf_csv = os.path.join(outdir, "pmf.csv")
        with open(pmf_csv, 'w', encoding='utf-8') as f:
            f.write("symbol,index,count,probability\n")
            for i, ch in enumerate(ALPHABET):
                cnt = self.counts.get(ch, 0)
                prob = self.pmfs.get(ch, 0.0)
                f.write(f"{ch},{i},{cnt},{prob:.12f}\n")

        # 3) BSC decoded text
        bsc_path = os.path.join(outdir, "bsc_received_decoded.txt")
        with open(bsc_path, 'w', encoding='utf-8') as f:
            f.write(''.join(self.bsc_decoded_chars))

        # 4) report
        rpt = os.path.join(outdir, "report.txt")
        with open(rpt, 'w', encoding='utf-8') as f:
            f.write(f"Source file: {self.results['file']}\n")
            f.write(f"Total symbols: {self.results['total_chars']}\n\n")
            f.write(f"H(X) = {self.results['H_x']:.12f} bits\n")
            f.write(f"D(P||U) = {self.results['D_PU']:.12f} bits\n")
            f.write(f"H(X,Y) = {self.results['H_xy']:.12f} bits\n")
            f.write(f"H(Y|X) = {self.results['H_y_given_x']:.12f} bits\n")
            f.write(f"Chain rule difference = {self.results['chain_diff']:.12e}\n")
            f.write(f"BSC p = {self.results['p_bsc']}, seed = {self.results['seed']}\n\n")
            f.write("Top counts:\n")
            for ch, cnt in sorted(self.counts.items(), key=lambda x: x[1], reverse=True)[:30]:
                display = "'space'" if ch == ' ' else ch
                f.write(f"  {display:8s} : {cnt} ({self.pmfs[ch]:.6f})\n")

        # 5) Save compressed file if exists
        if self.compressed_bitstring:
            enc_path = os.path.join(outdir, f"{base}_compressed.txt")
            payload = {
                'algorithm': self.compressed_algo,
                'codebook': self.compressed_codebook,
                'encoded_data': self.compressed_bitstring,
                'metadata': {
                    'source_file': os.path.basename(self.filepath.get() or ""),
                    'total_symbols': self.total_chars,
                    'timestamp': time.time()
                }
            }
            with open(enc_path, 'w', encoding='utf-8') as f:
                json.dump(payload, f)

        messagebox.showinfo("Saved", f"Results saved to {outdir}")

# -----------------------
# Run
# -----------------------
if __name__ == "__main__":
    app = EntropyBSCApp()
    app.mainloop()
