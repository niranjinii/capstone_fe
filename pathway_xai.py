def load_hallmark_pathways(gmt_path):
    """Parses a GMT file and returns a dictionary of pathway names to sets of gene symbols."""
    pathways = {}
    with open(gmt_path) as f:
        for line in f:
            parts = line.strip().split('\t')
            name = parts[0]
            genes = set(parts[2:])  # skip the URL field
            pathways[name] = genes
    return pathways

def build_pathway_vectors(pathways, active_gene_names, full_weight_vector):
    """
    Returns a dict: pathway_name -> weight sub-vector of length n.
    Genes IN the pathway keep their original weight.
    Genes NOT in the pathway are set to 0.
    """
    pathway_vectors = {}
    for name, gene_set in pathways.items():
        sub_vec = []
        for i, gene in enumerate(active_gene_names):
            if gene in gene_set:
                sub_vec.append(full_weight_vector[i])
            else:
                sub_vec.append(0)
        # Only include pathways with overlap (at least one non-zero weight)
        if any(v != 0 for v in sub_vec):  
            pathway_vectors[name] = sub_vec
    return pathway_vectors
