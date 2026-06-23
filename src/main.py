import time

from src.chunking import split_documents
from src.ingest import load_documents
from src.vectorstore import build_vectorstore


def main():
    total_start = time.time()

    print("=" * 50)
    print("STEP 1: Loading documents...")
    start = time.time()

    docs = load_documents()

    print(f"✓ Loaded {len(docs)} documents")
    print(f"Time taken: {time.time() - start:.2f} seconds\n")

    print("=" * 50)
    print("STEP 2: Splitting documents into chunks...")
    start = time.time()

    chunks = split_documents(docs)

    print(f"✓ Created {len(chunks)} chunks")
    print(f"Time taken: {time.time() - start:.2f} seconds\n")

    print("=" * 50)
    print("STEP 3: Starting vector store build...")
    print("This may take several minutes depending on the embedding model.")
    print(f"Embedding {len(chunks)} chunks...")
    print("Started at:", time.strftime("%H:%M:%S"))
    print()

    start = time.time()

    try:
        build_vectorstore(chunks)

        elapsed = time.time() - start

        print("\n✓ Vector store build completed")
        print(f"Vectorization time: {elapsed:.2f} seconds")

    except Exception as e:
        print("\n✗ ERROR during vector store build:")
        print(e)
        raise

    print("\n" + "=" * 50)
    print("✓ Indexing complete.")
    print(
        f"Total execution time: {time.time() - total_start:.2f} seconds"
    )
    print("=" * 50)


if __name__ == "__main__":
    main()