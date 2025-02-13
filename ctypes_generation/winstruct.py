import collections
import itertools

#WinStructType = collections.namedtuple('WinStructType', ['name'])

#Ptr = collections.namedtuple('Ptr', [''])


class BitFieldValue(object):
    def __init__(self, nb_bits):
        assert isinstance(nb_bits, int)
        self.nb_bits = nb_bits

    def __int__(self):
        return self.nb_bits

    # def generate_ctypes(self):
        # return self.nb_bits

class ComplexArrayExpression(object):
    def __init__(self):
        self.values = []
        self.names = []

    def add_token_to_expression(self, value, isname=False):
        self.values.append(value)
        if isname:
            try:
                int(value) # An INT ? ignore
            except ValueError:
                self.names.append(value)

    def get_names(self):
        return self.names

    def generate_ctypes(self):
        # if len(self.values) > 1:
            # import pdb;pdb.set_trace()
        return "({0})".format(" ".join(self.values))

class WinStructType(object):
    def __init__(self, name):
        self.name = name

    def __repr__(self):
        return "{0}({1})".format(type(self).__name__, self.name)

    def generate_ctypes(self):
        return self.name

class Ptr(object):

    def __init__(self, struct):
        self.type = struct
        self.name = struct.name

    def generate_ctypes(self):
        return "POINTER({0})".format(self.name)

    def __repr__(self):
        return "Ptr({0})".format(repr(self.type))


class WinStruct(object):
    ctypes_type = "Structure"
    def __init__(self, name, pack=None):
        self.name = name
        self.pack = pack
        self.fields = []
        self.typedef = {}

    def add_field(self, field):
        self.fields.append(field)

    def add_typedef(self, name):
        if self.name is None:
            self.name = name
        if name in self.typedef:
            raise ValueError("nop")
        self.typedef[name] = self

    def add_ptr_typedef(self, name):
        if self.name is None:
            raise ValueError("Anonymous struct first typedef ({0}) should not be a PTR type".format(name))
        if name in self.typedef:
            raise ValueError("Multiple typedef for <{0}>".format(name))
        self.typedef[name] = Ptr(self)

    def is_self_referencing(self):
        for type in [f[0] for f in self.fields]:
            if type.name == self.name:
                return True
            if type.name in self.typedef:
                return True
        return False

    def contains_anon_struct(self):
        return any(name is None for type,name,nb in self.fields)

    def prepare_anon_struct(self):
        new_fields = []
        code = []
        i = 0
        for type, name, nb in self.fields:
            if name is not None:
                new_fields.append((type, name, nb))
                continue
            i += 1
            # Should begin by "_ANON_" to trigger <generate_anonymous_union>
            if type.typedef:
                assert len(type.typedef) == 1, "Anonymous structure should have only one name"
                field_name = list(type.typedef)[0]
                type.typedef = {} # Remove typedef so that there is no use of it when genering the code for this anon-struct
            else:
                field_name = "anon_{0:02}".format(i)
            type.name = "_ANON_{0}_SUB_{1}_{2}".format(self.name, type.ctypes_type, i).upper()
            code.append(type.generate_ctypes()) # Generate class for the code
            # Replace the type name + field name in fields list

            new_fields.append((WinStructType(type.name), field_name, nb))
        self.fields = new_fields
        return "\n".join(code)

    def generate_selfref_ctypes_class(self):
        res = ["# Self referencing struct tricks"]
        res += ["""class {0}(Structure): pass""".format(self.name)]
        # res += [self.generate_anonymous_union()]
        res += [self.generate_typedef_ctypes()]

        if self.pack:
            res += ["{0}._pack_ = ".format(self.pack)]
        res += ["{0}._fields_ = [".format(self.name)]
        for (ftype, name, nb_rep) in self.fields:
            if isinstance(nb_rep, BitFieldValue):
                res += ['    ("{0}", {1}, {2}),'.format(name, ftype.generate_ctypes(), nb_rep.nb_bits)]
                continue
            elif isinstance(nb_rep, ComplexArrayExpression):
                nb_rep = nb_rep.generate_ctypes()
            if nb_rep == 1:
                res+= ['    ("{0}", {1}),'.format(name, ftype.generate_ctypes())]
            else:
                res+= ['    ("{0}", {1} * {2}),'.format(name, ftype.generate_ctypes(), nb_rep)]
        res += ["]"]
        return "\n".join(res)

    def generate_anonymous_union(self):
        annon_fields = [name for (ftype, name, nb_rep) in self.fields if ftype.name.startswith("_ANON_")]
        if not annon_fields:
            return ""
        if len(annon_fields) == 1:
            annon_fields_str = '"{0}",'.format(annon_fields[0])
        else:
            annon_fields_str = ",".join(['"{0}"'.format(name) for name in annon_fields])
        return "    _anonymous_ = ({0})\n".format(annon_fields_str)

    def generate_ctypes_class(self):
        res = "class {0}({1}):\n".format(self.name, self.ctypes_type)
        if self.pack:
            res += "    _pack_ = {0}\n".format(self.pack)
        res += self.generate_anonymous_union()
        res += "    _fields_ = [\n"""

        for (ftype, name, nb_rep) in self.fields:
            if isinstance(nb_rep, BitFieldValue):
                res += '    ("{0}", {1}, {2}),\n'.format(name, ftype.generate_ctypes(), nb_rep.nb_bits)
                continue
            elif isinstance(nb_rep, ComplexArrayExpression):
                # Should I check 'ftype' somewhere when we have a bitfield ?
                nb_rep = nb_rep.generate_ctypes()

            if nb_rep == 1:
                res+= '        ("{0}", {1}),\n'.format(name, ftype.generate_ctypes())
            else:
                res+= '        ("{0}", {1} * {2}),\n'.format(name, ftype.generate_ctypes(), nb_rep)
        res += "    ]"
        return res

    def generate_typedef_ctypes(self):
        typedef_ctypes = []
        for typedef_name, value in sorted(self.typedef.items()):
            str_value = self.name
            if typedef_name == str_value: # Do not generate "X= X" line (anonymous structs gen this)
                continue
            if type(value) == Ptr:
                str_value = "POINTER({0})".format(self.name)
            typedef_ctypes += ["{0} = {1}".format(typedef_name, str_value)]
        return "\n".join(typedef_ctypes)

    def generate_ctypes(self):
        anon_code = ""
        if self.contains_anon_struct():
            anon_code = self.prepare_anon_struct()

        if self.is_self_referencing():
            print("{0} is self referencing".format(self.name))
            return anon_code + self.generate_selfref_ctypes_class() + "\n"

        ctypes_class = self.generate_ctypes_class()
        ctypes_typedef = self.generate_typedef_ctypes()
        return anon_code + "\n".join([ctypes_class, ctypes_typedef]) + "\n"

class WinUnion(WinStruct):
    ctypes_type = "Union"

class WinEnum(object):
    def __init__(self, name):
        self.name = name
        self.fields = []
        self.typedef = {}

    def add_enum_entry(self, number, name):
        self.fields.append((number, name))

    def add_typedef(self, name):
        if self.name is None:
            # Setup our name to our first typedef
            self.name = name
        if name in self.typedef:
            raise ValueError("nop")
        self.typedef[name] = self

    def add_ptr_typedef(self, name):
        if self.name is None:
            raise ValueError("Anonymous enum first typedef ({0}) should not be a PTR type".format(name))
        if name in self.typedef:
            raise ValueError("nop")
        self.typedef[name] = Ptr(self)

    # Assert that enum are DWORD
    def generate_ctypes(self):
        #lines = ["{0} = DWORD".format(self.name)]
        lines = []
        for i, name in self.fields:
            lines.append('{0} = EnumValue("{2}", "{0}", {1})'.format(name, "{0:#x}".format(i), self.name))

        lines += ["class {0}(EnumType):".format(self.name)]
        lines += ["    values = [{0}]".format(", ".join([name for i, name in self.fields]))]
        lines += ["    mapper = FlagMapper(*values)".format(self.name)]

        for typedef_name, value in sorted(self.typedef.items()):
            str_value = self.name
            if typedef_name == str_value: # Do not generate "X= X" line (anonymous enum gen this)
                continue
            if type(value) == Ptr:
                str_value = "POINTER({0})".format(self.name)
            lines += ["{0} = {1}".format(typedef_name, str_value)]
        #lines += ["{0} = {1}".format(t, self.name) for t in self.typedef]
        lines += [""]
        ctypes_class = "\n".join(lines)
        return ctypes_class + "\n"
