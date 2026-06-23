from typing import Type, TypeVar, Any
from pydantic import BaseModel
from langchain_core.output_parsers import PydanticOutputParser
from langchain.output_parsers import RetryOutputParser
from langchain_core.prompts import PromptTemplate

T = TypeVar('T', bound=BaseModel)

def invoke_structured(
    llm: Any,
    prompt: Any,
    schema: Type[T],
    fallback: T,
    task_id: str,
    agent_name: str,
    input_kwargs: dict,
    strategy: str = "auto",
    allow_retry: bool = True
) -> T:
    """
    统一的结构化输出辅助函数。
    1. 尝试原生 structured_output
    2. 如果失败（可能模型不支持），使用 PydanticOutputParser
    3. 遇到解析错误，使用 RetryOutputParser 重试一次
    4. 兜底返回 fallback
    """
    from src.utils.logger import get_logger
    logger = get_logger("structured_output")
    
    # Try native structured output first
    if strategy != "parser":
        try:
            from src.utils.llm_semaphore import safe_invoke
            structured_llm = llm.with_structured_output(schema)
            chain = prompt | structured_llm
            result = safe_invoke(chain, input_kwargs)
            if isinstance(result, schema):
                return result
            # if not, fallback to parser
        except Exception as e:
            logger.warning(
                "Native structured output failed, falling back to PydanticOutputParser.",
                extra={"task_id": task_id, "agent": agent_name}
            )

    # Use parser
    parser = PydanticOutputParser(pydantic_object=schema)
    
    # Inject format instructions into prompt
    # The prompt could be ChatPromptTemplate, we append format_instructions
    try:
        if "format_instructions" not in prompt.input_variables:
            # Manually append if it doesn't have it
            if hasattr(prompt, "messages"):
                from langchain_core.prompts import HumanMessagePromptTemplate
                prompt.messages.append(
                    HumanMessagePromptTemplate.from_template("{format_instructions}")
                )
            else:
                prompt.template += "\n{format_instructions}"
                prompt.input_variables.append("format_instructions")
                
        input_kwargs["format_instructions"] = parser.get_format_instructions()
        chain = prompt | llm | parser
        
        try:
            from src.utils.llm_semaphore import safe_invoke
            res = safe_invoke(chain, input_kwargs)
            return res
        except Exception as parse_error:
            if not allow_retry:
                logger.warning(
                    f"First parse failed, retry disabled. Error: {parse_error}",
                    extra={"task_id": task_id, "agent": agent_name}
                )
                return fallback
                
            logger.warning(
                "First parse failed, initiating RetryOutputParser.",
                extra={"task_id": task_id, "agent": agent_name}
            )
            retry_parser = RetryOutputParser.from_llm(parser=parser, llm=llm, max_retries=1)
            # Invoke the model again to get the unparsed string, then retry
            raw_chain = prompt | llm
            from src.utils.llm_semaphore import safe_invoke
            raw_response = safe_invoke(raw_chain, input_kwargs)
            
            from langchain_core.prompts import PromptTemplate
            # We must pass the original prompt value as prompt_value to the retry parser
            prompt_value = prompt.invoke(input_kwargs)
            res = retry_parser.parse_with_prompt(raw_response.content, prompt_value)
            return res

    except Exception as e:
        logger.exception(
            "All structured output attempts failed.",
            extra={"task_id": task_id, "agent": agent_name, "error": str(e)}
        )
        return fallback
