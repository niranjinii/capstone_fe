import requests
import gzip
import os

URL = 'https://tcga.xenahubs.net/download/TCGA.PANCAN.sampleMap/EB%2B%2BAdjustPANCAN_IlluminaHiSeq_RNASeqV2.geneExp.xena.gz'
OUTPUT_FILE = 'gene_names_20531.txt'

def download_gene_names():
    print(f"Streaming {URL} to extract gene names...")
    
    # We will only read the first column of each line to save memory
    genes = []
    
    with requests.get(URL, stream=True) as r:
        r.raise_for_status()
        with gzip.GzipFile(fileobj=r.raw, mode='rb') as f:
            # The first line is the header (sample IDs), we skip it
            header = f.readline()
            
            # Read the rest of the lines
            count = 0
            for line in f:
                # Get the first column (before the first tab)
                first_col = line.split(b'\t', 1)[0].decode('utf-8')
                
                # Format is usually 'BRCA1|672' or just 'BRCA1'
                gene_symbol = first_col.split('|')[0]
                genes.append(gene_symbol)
                
                count += 1
                if count % 5000 == 0:
                    print(f"Read {count} genes...")
                    
    print(f"Finished reading. Total genes extracted: {len(genes)}")
    
    with open(OUTPUT_FILE, 'w') as out:
        for gene in genes:
            out.write(f"{gene}\n")
            
    print(f"Saved to {OUTPUT_FILE}")

if __name__ == '__main__':
    download_gene_names()
