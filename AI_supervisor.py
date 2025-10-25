# AI_supervisor.py
import os
import sys
import argparse
from pathlib import Path
from typing import Dict, Any, TypedDict

# Add the current directory to the Python path
current_dir = os.path.dirname(os.path.abspath(__file__))
if current_dir not in sys.path:
    sys.path.insert(0, current_dir)
	

# Set environment variables
os.environ["MODEL_CACHE_DIR"] = os.path.abspath("./models")
os.environ.pop('http_proxy', None)
os.environ.pop('https_proxy', None)

# Now import directly (no relative imports)
from content_validation import validate_content
from authenticity_validation import validate_authentication

from langgraph.graph import StateGraph, END


class ValidationState(TypedDict):
    input_path: str
    api_key: str
    content_validation_result: Dict[str, Any]
    authentication_validation_result: Dict[str, Any]
    final_decision: str
    reasoning: str


class DocumentValidationAgent:
    def __init__(self, api_key: str):
        self.api_key = api_key

    def run_content_validation(self, input_path: str) -> Dict[str, Any]:
        """Run content validation using content_validation module"""
        try:
            result = validate_content(self.api_key, input_path)
            return {
                "status": "success",
                "result": result,
                "message": f"Content Validation: {result.get('status', 'unknown')}"
            }
        except Exception as e:
            return {
                "status": "error",
                "result": None,
                "message": f"Content Validation Error: {str(e)}"
            }

    def run_authentication_validation(self, input_path: str) -> Dict[str, Any]:
        """Run authenticity validation using authenticity_validation module"""
        try:
            result = validate_authentication(self.api_key, input_path)
            return {
                "status": "success",
                "result": result.get("result"),
                "message": f"Authentication Validation: {result.get('result', {}).get('status', 'unknown')}"
            }
        except Exception as e:
            return {
                "status": "error",
                "result": None,
                "message": f"Authentication Validation Error: {str(e)}"
            }


def create_validation_workflow(api_key: str):
    """Create the LangGraph workflow for document validation"""
    agent = DocumentValidationAgent(api_key)

    def content_validation_node(state: ValidationState) -> ValidationState:
        print("🔍 Step 1: Content Validation...")
        result = agent.run_content_validation(state["input_path"])
        state["content_validation_result"] = result
        state["reasoning"] = f"Content validation: {result['status']}"
        return state

    def authentication_validation_node(state: ValidationState) -> ValidationState:
        print("🔐 Step 2: Authenticity Validation...")
        result = agent.run_authentication_validation(state["input_path"])
        state["authentication_validation_result"] = result
        state["reasoning"] += f" | Authenticity validation: {result['status']}"
        return state

    def decision_node(state: ValidationState) -> ValidationState:
        print("🎯 Step 3: Making Final Decision...")

        content_result = state.get("content_validation_result", {})
        auth_result = state.get("authentication_validation_result", {})

        # Extract validation status
        content_valid = (
            content_result.get("status") == "success" and
            content_result.get("result") and
            content_result.get("result", {}).get("status") == "validated"
        )

        auth_valid = (
            auth_result.get("status") == "success" and
            auth_result.get("result") and
            auth_result.get("result", {}).get("status") == "validated"
        )

        # Make final decision
        if content_valid and auth_valid:
            final_decision = "✅ Document is VALID - Passed both content and authenticity checks"
        elif content_valid and not auth_valid:
            final_decision = "⚠️ Document needs MANUAL REVIEW - Passed content but failed authenticity"
        elif not content_valid and auth_valid:
            final_decision = "⚠️ Document needs MANUAL REVIEW - Passed authenticity but failed content"
        else:
            final_decision = "❌ Document is INVALID - Failed both content and authenticity checks"

        state["final_decision"] = final_decision
        state["reasoning"] += f" | Final decision: {final_decision}"
        return state

    # Create workflow graph
    workflow = StateGraph(ValidationState)

    # Add nodes
    workflow.add_node("content_validation", content_validation_node)
    workflow.add_node("authentication_validation", authentication_validation_node)
    workflow.add_node("final_decision", decision_node)

    # Define edges
    workflow.set_entry_point("content_validation")
    workflow.add_edge("content_validation", "authentication_validation")
    workflow.add_edge("authentication_validation", "final_decision")
    workflow.add_edge("final_decision", END)

    return workflow.compile()


def run_document_validation(api_key: str, input_path: str):
    """Main function to run document validation using LangGraph agent"""
    print("🚀 Starting Document Validation Agent...")
    print(f"📄 Processing: {input_path}")
    print("-" * 50)

    # Create the LangGraph workflow
    app = create_validation_workflow(api_key)

    # Initial state
    initial_state = ValidationState(
        input_path=input_path.strip(),
        api_key=api_key,
        content_validation_result={},
        authentication_validation_result={},
        final_decision="",
        reasoning="Starting validation process"
    )

    # Execute the workflow
    final_state = app.invoke(initial_state)

    # Print comprehensive results
    print("\n" + "="*60)
    print("📊 LANGGRAPH VALIDATION RESULTS")
    print("="*60)
    content_result = final_state["content_validation_result"]
    auth_result = final_state["authentication_validation_result"]

    print(f"📝 Content Validation: {content_result.get('message', 'No result')}")
    print(f"🔐 Authenticity Validation: {auth_result.get('message', 'No result')}")
    print(f"🎯 {final_state['final_decision']}")
    print(f"🔍 Reasoning: {final_state['reasoning']}")

    return final_state


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Document Validation Agent System")
    parser.add_argument("input_path", type=str, help="Input PDF, image, or markdown file")
    parser.add_argument("--api_key", type=str, required=True, help="API key for LLM service")

    args = parser.parse_args()

    result = run_document_validation(args.api_key, args.input_path.strip())
    print(f"\n✅ LangGraph Agent Execution Completed!")