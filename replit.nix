{ pkgs }: {
  # Native runtime libraries for ONNX Runtime, OpenCV headless and PDFium wheels.
  deps = [ pkgs.stdenv.cc.cc.lib pkgs.zlib ];
  env = {
    LD_LIBRARY_PATH = pkgs.lib.makeLibraryPath [
      pkgs.stdenv.cc.cc.lib
      pkgs.zlib
    ];
  };
}
