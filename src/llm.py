from langchain_huggingface import HuggingFacePipeline
from transformers import pipeline


def get_llm():
    hf_pipeline = pipeline(
        "text-generation",
        model="Qwen/Qwen2.5-0.5B-Instruct",
        max_new_tokens=256,
        temperature=0.2
    )

    return HuggingFacePipeline(pipeline=hf_pipeline)