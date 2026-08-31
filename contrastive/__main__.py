import sys

from parsing import parse_annotated
from engine import Engine
from search import enumerate_explanations

def main():
    if len(sys.argv) < 2:
        print("ERROR: Missing file path.")
        sys.exit(1)
        
    file_path = sys.argv[1]
    
    try:
        with open(file_path, 'r', encoding='utf-8') as file:
            program_annotated = file.read()
    except Exception as e:
        print(f"Error reading file: {e}")
        sys.exit(1)


    cep = parse_annotated(program_annotated)
    engine = Engine(cep)
    expls = enumerate_explanations(engine)
    num_expls = len(expls)
    print(f"Found {len(expls)} explanations.")
    for i in range(num_expls):
        print(40*"=")
        print(f"EXPLANATION {i+1}")
        print(str(expls[i]))

if __name__ == '__main__':
    main()