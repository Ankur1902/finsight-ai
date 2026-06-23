from langchain_huggingface import HuggingFaceEmbeddings

def get_embeddings():
    return HuggingFaceEmbeddings(
        model_name="BAAI/bge-m3",
         encode_kwargs={"normalize_embeddings": True},
    )