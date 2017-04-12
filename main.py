from __future__ import print_function
import sys

# This is not required if you've installed pycparser into
# your site-packages/ with setup.py
sys.path.extend(['.', '..'])

importError = False;

try:
	from pycparser import c_parser, c_ast, parse_file
except ImportError:
	print("Please install PyCParser");
	importError = True;

try:
	import numpy as np
except ImportError:
	print("Please install numpy");
	importError = True;

try:
	import graphviz as gv
except ImportError:
	print("Please install GraphViz");
	importError = True;

try:
	import matplotlib.pyplot as plt
except ImportError:
	print("Please install MatPlotLib");
	importError = True;

if (importError):
	sys.exit(1);


methodQueue = [];		#Queue of tuples (methodName, methodNode) of methods we're tracing.  methodNode is the CFGNode of the method
rootNode 	= None;		#The root of our tree

funcCalls 	= {};		# FunctionName: [List of FuncCall nodes for that function]
						#Using a dictionary to keep track of function call nodes allows us to scale with size, rather than time
						#The problem with using this is that we can no longer get a parent tree, we would
						# need to find another way to deal with the upwards trace/parent links

funcDefCFGNodes = {}	# FunctionName: CFGNode


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
	def __init__(self, funcname, startingNode):
		"""Store information we'll need here"""
		self.funcname 		= funcname 			#The name of the function call nodes we are looking for
		self.currentCFGNode = startingNode;		#
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
				conditionsAndLoops = [];	#Holds CFGNodes (in order) that represent if/else/switch/for/while
				inIfRecurse = False;
				while (not isinstance(isDefinedIn, c_ast.FuncDef)):
					if (isinstance(isDefinedIn, c_ast.FileAST)):	#If we get to the top of the AST something really bad happened
						print("ERROR (FATAL): upward parent trace reached FileAST node");
						sys.exit();

					#TODO: Figure out how if/elif/elif/elif/else works and update logic
					if (isinstance(isDefinedIn, c_ast.If)):
						#Get the BinaryOP and then the string representing it
						conditionString = resolveToString(isDefinedIn.cond);

						#Get the compound reperesenting the outcome of this if's flow that we came from
						ifCompound = self.parentList[numberAboveCurrent + 1];

						#If we're in an If recurse or the compound was the false part of the if/else, this must resolve to false
						if (inIfRecurse or ifCompound is isDefinedIn.children()[2]):
							conditionString += " is False";

						#If the compound we just came form is 1st child, the if statement BinaryOp must be true
						elif (ifCompound is isDefinedIn.children()[1]):
							conditionString += " is True";

						#Indicate we may be in an upwards recusive if/else if/else tree
						inIfRecurse = True;

					#TODO: Logic for dealing with switch statements goes here
					elif (isinstance(isDefinedIn, c_ast.Switch)):
						#isDefinedIn.cond is the BinaryOp object
						inIfRecurse = False;

					#TODO: Logic for dealing with for loops goes here
					elif (isinstance(isDefinedIn, c_ast.For)):
						inIfRecurse = False;

					#TODO: Logic for dealing with while loops goes here
					elif (isinstance(isDefinedIn, c_ast.While)):
						inIfRecurse = False;

					#TODO: Logic for dealing with dowhile loops goes here
					elif (isinstance(isDefinedIn, c_ast.DoWhile)):
						inIfRecurse = False;

					else:
						inIfRecurse = False;

					numberAboveCurrent -= 1;
					isDefinedIn = self.parentList[numberAboveCurrent];

				#Get the name and location of the function we are in
				methodName = isDefinedIn.decl.name;
				methodLocation = isDefinedIn.decl.coord;

				#Something really bad happened for us to not find the name for this FuncDef node
				if (methodName is None):
					print("ERROR (FATAL): unable to locate function name holding call to " + self.funcname);
					sys.exit();

				newNode = None;
				if (methodName in funcDefCFGNodes.keys()):
					newNode = funcDefCFGNodes[methodName];

				#Make a CFG node for this "new" node, and add it to the methodQueue only if it is not already in the methodQueue
				if (not any(entry[0] == methodName for entry in methodQueue) ):
					if (newNode is None):
						newNode = CFGNode(methodName, isDefinedIn);			#Make the new CFGNode
						funcDefCFGNodes[methodName] = newNode;

					self.currentCFGNode.add_child(newNode);				#Add the new CFGNode as a child of the current CFGNode
					newNode.add_parent(self.currentCFGNode);			#Add the current CFGNode as a parent of the new CFGNode
					methodQueue.append( (methodName, newNode) );		#Add the method we found it in to the methodQueue
				else:
					self.currentCFGNode.add_child(funcDefCFGNodes[methodName]);
					funcDefCFGNodes[methodName].add_parent(self.currentCFGNode);

				print('%s called at %s inside %s declared at %s\n' % (self.funcname, node.name.coord, methodName, methodLocation))

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

		#We found our node on the line, don't do anything more
		if (self.ast_node is not None):
			return;

		#
		if (isinstance(node, c_ast.FuncCall)):
			global funcCalls;
			if (node.name not in funcCalls.keys()):
				funcCalls[node.name] = []
			funcCalls[node.name].append(node);

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
				self.ast_node = node;
				return;

		#If this node didn't give us the line number, go to all its children
		if (self.ast_node is None):
			for c_name, c in node.children():
				self.visit(c);


def parseBinaryOp(binOp):
	"""Returns a string representing the condition for the condition tree specified, binOP is a BinaryOP object"""
	
	#TODO: Make this deal with groupings of conditionals
	#		E.g. if ( (x > 10 || y > 1) && z == 1 )

	#ifRoot.left goes before the current string, ifRoot.left goes after the current string
	string = binOp.op;

	#If the child is a BinaryOP we need to recurse again
	if (isinstance(binOp.left, c_ast.BinaryOp)):
		string = (parseBinaryOp(binOp.left) + string);
	else:
		string = (resolveToString(binOp.left) + string);

	if (isinstance(binOp.right, c_ast.BinaryOp)):
		string += parseBinaryOp(binOp.right);
	else:
		string += resolveToString(binOp.right);

	print("parseBinaryOP returning '%s'" % (string));
	return string;


#TODO
def resolveToString(node):
	"""Takes the PyCParser node and returns a string representation of it"""
	#TODO: the better way to do this would be by anonymous function
	#		the methods would be toStringNODECLASS(node):
	#		You'd simply append the name of the node class to 'toString' and call it, no giant if/elif need
	#TODO: only include the nodes we actually need (or not, as we don't know what we'll need)
	#NOTE: Even easier would be if these classes just had a damn __str__ method!!!!!!!!

	#ArrayDecl
	#ArrayRef
	#Assignment
	#BinaryOp
	if (isinstance(node, c_ast.BinaryOp)):
		return parseBinaryOp(node);
	#Break
	#Case
	#Cast
	#Compound
	#CompoundLiteral
	#Constant
	if (isinstance(node, c_ast.Constant)):
		return node.value;
	#Continue
	#Decl
	#DeclList
	#Default
	#DoWhile
	#EllipsisParam
	#EmptyStatement
	#Enum
	#Enumerator
	#EnumeratorList
	#ExprList
	#FileAST
	#For
	#FuncCall 	NOTE: not actually sure what would happen here?
	#FuncDecl
	#FuncDef
	#Goto
	#ID
	if (isinstance(node, c_ast.ID)):
		return node.name;
	#IdentifierType
	#If
	#InitList
	#Label
	#NamedInitializer
	#ParamList
	#PtrDecl
	#Return
	#Struct
	#StructRef
	#Switch
	#TernaryOp
	#TypeDecl
	#Typedef
	#Typename
	#UnaryOp
	#Union
	#While
	#Pragma


#
#For each methodName, methodNode in methodQueue:
#	Find each instance of the function call, put those in a queue
#	For each instance, find what function that call is inside of
#Repeat these steps using the new function each time until we reach main on all instances
#
def parseForCFG(filename, lineNo):
	"""Parse the file filename for a Control Flow Graph starting at lineNo"""

	#Create the AST to parse
	ast = parse_file(filename, use_cpp=True);

	#Given the line number, find the node of that line number
	lnv = LineNumberVisitor(lineNo);
	lnv.visit(ast);
	vulnerableNode = lnv.ast_node;	#The node on the specified line
	if (vulnerableNode == None):
		print("ERROR (FATAL): unable to retrieve node for line " + str(lineno));
		sys.exit();
	
	global rootNode;
	rootNode = CFGNode("Line " + str(lineNo), None);
	lineFuncNode = CFGNode(lnv.lastFuncDefName, lnv.lastFuncDefNode);
	rootNode.add_child(lineFuncNode);
	lineFuncNode.add_parent(rootNode);

	#Add those to the methodQueue
	methodQueue.append( (lnv.lastFuncDefName, lineFuncNode) );

	#Parse continually while we have methods to look for in the methodQueue
	v = FuncCallVisitor('', None);
	while (methodQueue):
		methodName, methodNode = methodQueue.pop(0);
		v.funcname = methodName;
		v.currentCFGNode = methodNode;
		v.parentList = [];
		v.visit(ast)

	print();
	print();
	rootNode.print_tree(0);

	return rootNode;


def visualize(fileName, rootNode, direction):
	"""Plots the tree starting at 'rootNode' is a visually pleasing format using GraphViz
		fileName: the name of the file in which the visual of the graph will be stored
		rootNode: the start of the graph to visualize
		direction: do we display from start->vulnerability (0) or vulnerability->start (1)?
	"""
	G = gv.Digraph('G', filename=fileName);

	stack = [rootNode];
	while (stack):
		curr_node = stack.pop(0);

		#Add a link from parent to child
		for child in curr_node.children:
			stack.append(child);

			#To go from start of program to vulnerable point swap these two arguments
			if (direction == 0):
				G.edge(child.function, curr_node.function);
			elif (direction == 1):
				G.edge(curr_node.function, child.function);
			else:
				print("ERROR: incorrect direction to visualize: " + str(direction));
				print("\tDirection should be 0 or 1");
				return;

	G.view();



def visualizeAST(rootNode, fileName):
	G = gv.Digraph('G', filename=("AST" + fileName));

	stack = [rootNode];
	while (stack):
		curr_node = stack.pop(0);
		nodeName1 = curr_node.__class__.__name__;
		if (curr_node.attr_names):
			vlist = [getattr(curr_node, n) for n in curr_node.attr_names]
			attrstr = ', '.join('%s' % v for v in vlist)
			nodeName1 += (': ' + attrstr);
		
		for c, child in curr_node.children():
			stack.append(child);

			nodeName2 = child.__class__.__name__;
			if (child.attr_names):
				vlist = [getattr(child, n) for n in child.attr_names]
				attrstr = ', '.join('%s' % v for v in vlist)
				nodeName2 += (': ' + attrstr);
			G.edge(nodeName1, nodeName2);

	G.view();


if __name__ == "__main__":
	try:
		if len(sys.argv) == 3:	#programName filename linenumber
			filename = sys.argv[1];
			try:
				lineno = int(sys.argv[2]);
			except ValueError:
				print("LineNumber should be an integer");
				sys.exit();
		else:
			filename = 'third.c';
			lineno = 16;

		print("FileName: " + filename);
		print("LineNo: " + str(lineno));

		CFG = parseForCFG(filename, lineno)
		visualize(filename + "DOT", CFG, 0);
	except KeyboardInterrupt:
		exit();