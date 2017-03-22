from __future__ import print_function
import sys

# This is not required if you've installed pycparser into
# your site-packages/ with setup.py
sys.path.extend(['.', '..'])

from pycparser import c_parser, c_ast, parse_file

methodQueue = [];	#Queue of tuples (methodName, methodNode) of methods we're tracing.  methodNode is the CFGNode of the method
rootNode 	= None;	#The root of our tree
currentNode = rootNode;


class CFGNode():
	"""
	Currently represents a function call
	Root node: function as "", parents as empty, children as not empty, and info as None
	'Root' is technically the vulnerable point we start at
	The exit nodes will have children as empty and parents as not
	"""
	def __init__(self, funcname, ast_info):
		self.function	= funcname;	#The name of the function this node represents
		self.parents 	= [];		#List of CFGNode that call this function (who calls this function)
		self.children 	= [];		#List of CFGNode called by this function (who this function calls)
		self.info 		= ast_info;	#Info about said node, most likely will be the actual AST node

	def __repr__(self):
		return self.function;

	def __str__(self):
		return self.function;

	def add_child(self, child):
		"""Add a child node to this node"""
		self.children.append(child);

	def add_parent(self, parent):
		"""Add a parent node to this node"""
		self.parents.append(parent);

	def print_tree(self, spaces):
		"""Textual version of the CFG from this node downward"""
		print(spaces*" " + self.__str__());	#2 spaces per level
		for child in self.children:
			child.print_tree(spaces + 2);


class FuncCallVisitor(c_ast.NodeVisitor):
	"""Used to interact with all FuncCall nodes"""
	def __init__(self, funcname):
		"""Store information we'll need here"""
		self.funcname 		= funcname
		self.current_parent = None;

		global rootNode;
		self.currentCFGNode = rootNode;
		self.parentList = [];	#Keeps track of the list of nodes we've seen on this path in the AST (works b/c generic_visit is DFS)

	def visit_FuncCall(self, node):
		"""Triggers every time we find a FuncCall node in PyCParser's AST"""
		#If this node is of the function we are looking for
		if node.name.name == self.funcname:
			#Check if this method is already in the parent node's children, if so we don't need to add it again, if not add it
			#NOTE: We probably want to know all calls inside a method as well as the line numbers those calls are on
			if ( not any(x.function == node.name.name for x in self.currentCFGNode.parents) ):
				#self.currentCFGNode.add_parent( CFGNode(node.name.name, node) );
				
				#Upwards trace of c_ast nodes until we find the FuncDef that 'node' is inside of
				numberAboveCurrent = -1;
				isDefinedIn = self.parentList[numberAboveCurrent];
				while (not isinstance(isDefinedIn, c_ast.FuncDef)):
					if (isinstance(isDefinedIn, c_ast.FileAST)):	#If we get to the top of the AST something really bad happened
						print("ERROR (FATAL): upward parent trace reached FileAST node");
						sys.exit();

					numberAboveCurrent -= 1;
					isDefinedIn = self.parentList[numberAboveCurrent];

				#Get the name and location of the function we are in
				methodName = isDefinedIn.decl.name;
				methodLocation = isDefinedIn.decl.coord;

				#Something really bad happened for us to not find the name for this FuncDef node
				if (methodName is None):
					print("ERROR (FATAL): unable to locate function name holding call to " + self.funcname);
					sys.exit();

				#Make a CFG node for this "new" node, and add it to the methodQueue only if it is not already in the methodQueue
				if (not any(entry[0] == methodName for entry in methodQueue) ):
					newNode = CFGNode(methodName, isDefinedIn);			#Make the new CFGNode
					self.currentCFGNode.add_child(newNode);				#Add the new CFGNode as a child of the current CFGNode
					newNode.add_parent(currentNode);					#Add the current CFGNode as a parent of the new CFGNode
					methodQueue.append( (methodName, newNode) );		#Add the method we found it in to the methodQueue

					self.currentCFGNode = newNode;

				print('%s called at %s inside %s declared at %s' % (self.funcname, node.name.coord, methodName, methodLocation))

		#Visit all children of this node
		FuncCallVisitor.generic_visit(self, node);

	def generic_visit(self, node):
		"""Overrides the standard generic_visit method to keep track of the parent listings,
		   which are accessed while traversing"""

		#We are about to move down another level, so add this node to the parentList
		self.parentList.append(node);
		
		#Go through all of this node's children
		for c_name, c in node.children():
			self.visit(c);

		#We just finished all children, and are about to move up a level, so remove this node from the parentList
		self.parentList.pop(-1);


class LineNumberVisitor(c_ast.NodeVisitor):
	"""This class' sole purpose is to find the first c_ast node on a certain line number"""

	def __init__(self, linenumber):
		self.lineno 	= linenumber;	#The line number we are looking for
		self.ast_node 	= None;			#The node found on the specified linenumber
		self.lastFuncDefName = None;	#The name of the function this line number is inside of
		self.lastFuncDefNode = None;	#The FuncDef node this line number is inside of

	def generic_visit(self, node):
		"""Overrides the standard generic_visit to find the node on the specified line number"""

		#We will never need to find the FileAST node
		if (not isinstance(node, c_ast.FileAST)):
			#Keeps track of the function we are currently inside of
			if (isinstance(node, c_ast.FuncDef)):
				self.lastFuncDefNode = node;

				#Find the name of the function (based on the above processing) that 'node' is inside of
				for c_name, child in node.children():	#Now we have the FuncDef node of the method we are in
					if (isinstance(child, c_ast.Decl)):			#Found where the node's name is stored
						self.lastFuncDefName = child.name;
						break;

			#Don't do anything if we've already found a node on that line number
			if (self.ast_node is not None):
				return;

			#Figure out if we have a node from that line number
			lineNumber = node.coord.line;
			if (lineNumber is not None and lineNumber == self.lineno):
				print("Located node on line " + str(lineNumber));
				self.ast_node = node;
				return;

		#If this node didn't give us the line number, go to all its children
		if (self.ast_node is None):
			for c_name, c in node.children():
				self.visit(c);


#
#For each methodName, methodNode in methodQueue:
#	Find each instance of the function call, put those in a queue
#	For each instance, find what function that call is inside of
#Repeat these steps using the new function each time until we reach main on all instances
#
def parseForCFG(filename, lineNo):
	"""Parse the file filename for a Control Flow Graph starting at lineNo"""
	global rootNode;
	rootNode = CFGNode("", None)

	#Create the AST to parse
	ast = parse_file(filename, use_cpp=True)

	#Given the line number, find the node of that line number
	lnv = LineNumberVisitor(lineNo);
	lnv.visit(ast);
	vulnerableNode = lnv.ast_node;	#The node on the specified line
	if (vulnerableNode == None):
		print("ERROR (FATAL): unable to retrieve node for line " + str(lineno));
		sys.exit();

	#Trace that upwards once to get the (methodName, methodNode) that the specified line is inside of
	

	#Add those to the methodQueue
	methodQueue.append( (lnv.lastFuncDefName, lnv.lastFuncDefNode) );

	#Parse continually while we have methods to look for in the methodQueue
	while (methodQueue):
		methodName, methodNode = methodQueue.pop(0);
		v = FuncCallVisitor(methodName);
		v.visit(ast)

	return rootNode;


if __name__ == "__main__":
	try:
		if len(sys.argv) > 3:	#programName filename linenumber
			filename = sys.argv[1];
			try:
				lineno = int(sys.argv[2]);
			except ValueError:
				print("LineNumber should be an integer");
				sys.exit();
		else:
			filename = 'testCFile.c';
			lineno = 26;

		print("FileName: " + filename);
		print("LineNo: " + str(lineno));

		CFG = parseForCFG(filename, lineno)
	except KeyboardInterrupt:
		exit();