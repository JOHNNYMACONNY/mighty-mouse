import sys, os, json, yaml
from gemini_client import GeminiClient
from response_parser import ResponseParser

def solve(p_cfg_path, t_path):
    with open(p_cfg_path, 'r') as f: p_cfg = yaml.safe_load(f)
    with open(t_path, 'r') as f: task = json.load(f)
    
    tid = task.get('id', 'unknown')
    print(f"[*] Solving task {tid}...")
    
    # 1. Assemble System Instruction (Milestone 7 Optimization Path)
    segments = p_cfg.get('prompt_segments', [])
    sys_instr = ""
    for seg_file in segments:
        seg_path = os.path.join(os.path.dirname(p_cfg_path), seg_file)
        if os.path.exists(seg_path):
            with open(seg_path, 'r') as f: sys_instr += f.read() + "\n"
    
    # 2. Assemble User Prompt
    feedback_file = "logs/feedback.txt"
    feedback = ""
    if os.path.exists(feedback_file):
        with open(feedback_file, 'r') as f: feedback = f.read()
    
    user_prompt = f"Implement the following task:\n{json.dumps(task, indent=2)}\n"
    if feedback:
        user_prompt += f"\n\nPREVIOUS ATTEMPT FAILED. Feedback:\n{feedback}\nPlease correct your implementation."

    # 3. Call LLM (or Mock)
    client = GeminiClient()
    response = client.generate_content(sys_instr, user_prompt)
    
    if not response:
        print("[!] No response from model.")
        return False

    # 4. Parse and Write (Correct Method Name)
    parser = ResponseParser()
    parser.parse_and_write(response)
    print(f"[*] Task {tid} implementation applied.")
    return True

if __name__ == "__main__":
    if len(sys.argv) < 3:
        print("Usage: python3 mighty_mouse_agent.py <config> <task>")
        sys.exit(1)
    solve(sys.argv[1], sys.argv[2])
