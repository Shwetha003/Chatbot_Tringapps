from fastembed import TextEmbedding


# Load model once
embedding_model = TextEmbedding(
    model_name="BAAI/bge-small-en-v1.5"
)


def create_embedding(text: str):

    embedding = list(
        embedding_model.embed([text])
    )[0]

    return embedding.tolist()