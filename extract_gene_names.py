import urllib.request
import tarfile
import io
import os

URL = 'https://archive.ics.uci.edu/ml/machine-learning-databases/00401/TCGA-PANCAN-HiSeq-801x20531.tar.gz'
OUTPUT_FILE = 'gene_names_20531.txt'

import ssl

def download_and_extract_headers():
    print(f"Downloading {URL}...")
    req = urllib.request.Request(URL, headers={'User-Agent': 'Mozilla/5.0'})
    ctx = ssl.create_default_context()
    ctx.check_hostname = False
    ctx.verify_mode = ssl.CERT_NONE
    with urllib.request.urlopen(req, context=ctx) as response:
        print("Extracting tar.gz stream...")
        with tarfile.open(fileobj=response, mode='r|gz') as tar:
            for member in tar:
                if member.name.endswith('data.csv'):
                    print(f"Found {member.name}. Extracting header...")
                    f = tar.extractfile(member)
                    if f is not None:
                        # Read the first line (header)
                        header = f.readline().decode('utf-8').strip()
                        # The first column is usually 'Unnamed: 0', the rest are gene names
                        genes = header.split(',')[1:]
                        
                        print(f"Extracted {len(genes)} gene names.")
                        
                        with open(OUTPUT_FILE, 'w') as out_f:
                            for gene in genes:
                                # Clean names like "BRCA1|672" -> "BRCA1"
                                clean_name = gene.split('|')[0].strip('"')
                                out_f.write(f"{clean_name}\n")
                                
                        print(f"Saved cleaned gene names to {OUTPUT_FILE}")
                        return
                    
    print("Error: data.csv not found in the archive.")

if __name__ == '__main__':
    if not os.path.exists(OUTPUT_FILE):
        download_and_extract_headers()
    else:
        print(f"{OUTPUT_FILE} already exists. Skipping download.")
