import csv

input_file = 'gene_mapping_dictionary.csv'
output_file = 'gene_names_20531.txt'

genes = []
with open(input_file, 'r') as f:
    reader = csv.reader(f)
    next(reader)  # Skip header
    for row in reader:
        # row[1] is the Biological_Name
        gene = row[1].strip()
        # If it's '?', we can keep it as '?' or leave it as is, since it won't match any pathways anyway
        genes.append(gene)

with open(output_file, 'w') as f:
    for gene in genes:
        f.write(gene + '\n')

print(f"Successfully extracted {len(genes)} biological names and saved to {output_file}.")
