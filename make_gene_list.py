import numpy as np
import pandas as pd
import sys

# 1. Load the 33-cancer weight matrix
weights_file = 'master_33_cancer_weights.npy'
print(f"Loading weights from {weights_file}...")
W = np.load(weights_file)

# 2. Get the full list of 20,531 gene names
# Adjust the file name below if your gene file uses a different name
gene_names_file = 'EB++AdjustPANCAN_IlluminaHiSeq_RNASeqV2.geneExp.xena'

try:
    print(f"Loading gene names from {gene_names_file}...")
    gene_names = pd.read_csv(gene_names_file, sep='\t', usecols=[0]).iloc[:, 0].values
except FileNotFoundError:
    # Fallback to UCI data file if Xena isn't in the root directory
    gene_names_file = 'TCGA-PANCAN-HiSeq-801x20531/data.csv'
    print(f"Xena file not found. Loading gene names from {gene_names_file}...")
    gene_names = pd.read_csv(gene_names_file, nrows=0, index_col=0).columns.values

# 3. Find all non-zero (active) gene indices across all 33 cancer models
active_indices = np.flatnonzero(np.any(W != 0, axis=0))

# 4. Clean and format the gene symbols (e.g., 'BRCA1|672' -> 'BRCA1')
active_symbols = sorted(list(set(
    str(gene_names[i]).split('|')[0].strip() 
    for i in active_indices 
    if str(gene_names[i]).strip()
)))

# 5. Write to genes_cancer2.txt (one gene symbol per line)
output_file = 'genes_cancer2.txt'
with open(output_file, 'w') as f:
    for symbol in active_symbols:
        f.write(f"{symbol}\n")

print(f"SUCCESS: Extracted {len(active_symbols)} unique active gene symbols.")
print(f"Saved to '{output_file}'.")

