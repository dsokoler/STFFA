void foo(char* b);
void bar(char* f);
void foobar();

int main(int argc, char* argv[]) {
	int x = 5;

	if (x > 10) {
		foo(argv[1]);
	}
	else {
		bar(argv[1]);
	}

}

void foo(char* b) {
	foobar();
}

void bar(char* f) {
	foobar();
}

void foobar() {
	int vuln = 5;
}