# SPDX-FileCopyrightText: <text>Copyright 2026 Arm Limited and/or its
# affiliates <open-source-office@arm.com></text>
# SPDX-License-Identifier: MIT
#my $texmfdist = `kpsewhich -var-value=TEXMFDIST`;
#chomp($texmfdist);

#-M \"$texmfdist/xindy/modules\" 
#$makeindex = "xindy -L english -C utf8 -o %D %S";
# Use xindy for indexing (UTF-8)
$makeindex = 'xindy -L english -C utf8 -M /usr/share/texlive/texmf-dist/xindy/modules/lang/english/utf8.xdy -o %D %S';

