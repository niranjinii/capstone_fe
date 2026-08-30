CANCER_TYPES = [
    "ACC", "BLCA", "BRCA", "CESC", "CHOL", "COAD", "DLBC", "ESCA",
    "GBM", "HNSC", "KICH", "KIRC", "KIRP", "LAML", "LGG", "LIHC",
    "LUAD", "LUSC", "MESO", "OV", "PAAD", "PCPG", "PRAD", "READ",
    "SARC", "SKCM", "STAD", "TGCT", "THCA", "THYM", "UCEC", "UCS", "UVM"
]

# Production bucket dimensions based on true active gene counts
BUCKETS = {
    "small": {
        "max_dim": 100,
        "cancers": ["THYM", "GBM", "KICH", "PCPG", "TGCT", "DLBC", "UVM", "PAAD", "LAML", "PRAD"]
    },
    "medium": {
        "max_dim": 150,
        "cancers": [
            "CHOL", "READ", "LIHC", "COAD", "UCS", "THCA", "MESO", "HNSC",
            "OV", "LUAD", "ACC", "STAD", "SKCM"
        ]
    },
    "large": {
        "max_dim": 300,
        "cancers": ["LGG", "SARC", "KIRP", "ESCA", "LUSC", "UCEC", "KIRC", "BRCA", "BLCA", "CESC"]
    }
}