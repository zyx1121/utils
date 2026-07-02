#!/usr/bin/env swift
// subject-lift — macOS Vision subject lifting (background removal) via VNGenerateForegroundInstanceMaskRequest.
// Class-agnostic: people, pets, food, drinks, objects — whatever Vision judges a salient
// foreground instance, no fixed label set. Requires macOS 14+. No TCC prompt, no code
// signing needed — pure Vision.framework + CoreImage.
//
// Known limitation: `swift <file>.swift` runs in interpreted mode — every invocation pays
// a ~1-2s compile step plus a few seconds for the Vision model to load on first use.
// That's expected, not a bug.

import Foundation
import Vision
import CoreImage
import UniformTypeIdentifiers
import AppKit

func usage() {
    print("""
    subject-lift — macOS Vision subject lifting (background removal)

    Usage:
      utils subject-lift <input-image> <output-png>
      utils subject-lift -h | --help

    Examples:
      utils subject-lift cat.jpg cat-cutout.png
      utils subject-lift photo.heic subject.png

    Detects every salient foreground instance (person, pet, food, object — no
    fixed class list, whatever Vision finds) and writes a PNG with alpha:
    subject pixels opaque, everything else transparent. Prints the instance
    count and output dimensions to stdout.

    Exits non-zero if the input can't be read or if Vision finds zero instances.
    """)
}

let args = CommandLine.arguments

if args.contains("-h") || args.contains("--help") {
    usage()
    exit(0)
}

guard args.count == 3 else {
    FileHandle.standardError.write("subject-lift: expected <input-image> <output-png>, got \(args.count - 1) arg(s) — try --help\n".data(using: .utf8)!)
    exit(2)
}

let inputPath = args[1]
let outputPath = args[2]
let outputURL = URL(fileURLWithPath: outputPath)

guard FileManager.default.fileExists(atPath: inputPath) else {
    FileHandle.standardError.write("subject-lift: no such file: \(inputPath)\n".data(using: .utf8)!)
    exit(2)
}

guard let inputImage = NSImage(contentsOfFile: inputPath) else {
    FileHandle.standardError.write("subject-lift: failed to load \(inputPath) — is it a real image file?\n".data(using: .utf8)!)
    exit(2)
}

guard let cgImage = inputImage.cgImage(forProposedRect: nil, context: nil, hints: nil) else {
    FileHandle.standardError.write("subject-lift: failed to get a bitmap representation of \(inputPath)\n".data(using: .utf8)!)
    exit(1)
}

let handler = VNImageRequestHandler(cgImage: cgImage, options: [:])
let request = VNGenerateForegroundInstanceMaskRequest()

do {
    try handler.perform([request])
} catch {
    FileHandle.standardError.write("subject-lift: Vision request failed: \(error)\n".data(using: .utf8)!)
    exit(1)
}

guard let observation = request.results?.first as? VNInstanceMaskObservation else {
    FileHandle.standardError.write("subject-lift: no instance mask observation returned\n".data(using: .utf8)!)
    exit(1)
}

let allInstances = observation.allInstances

guard !allInstances.isEmpty else {
    FileHandle.standardError.write("subject-lift: zero instances detected in \(inputPath) — nothing to lift\n".data(using: .utf8)!)
    exit(1)
}

print("detected instances: \(allInstances.count)")

do {
    let maskedPixelBuffer = try observation.generateMaskedImage(
        ofInstances: allInstances,
        from: handler,
        croppedToInstancesExtent: false
    )

    let ciImage = CIImage(cvPixelBuffer: maskedPixelBuffer)
    let ciContext = CIContext()

    guard let outputCGImage = ciContext.createCGImage(ciImage, from: ciImage.extent) else {
        FileHandle.standardError.write("subject-lift: failed to rasterize the masked result\n".data(using: .utf8)!)
        exit(1)
    }

    guard let destination = CGImageDestinationCreateWithURL(outputURL as CFURL, UTType.png.identifier as CFString, 1, nil) else {
        FileHandle.standardError.write("subject-lift: failed to open \(outputPath) for writing\n".data(using: .utf8)!)
        exit(1)
    }

    CGImageDestinationAddImage(destination, outputCGImage, nil)
    guard CGImageDestinationFinalize(destination) else {
        FileHandle.standardError.write("subject-lift: failed to write PNG to \(outputPath)\n".data(using: .utf8)!)
        exit(1)
    }

    print("wrote \(outputPath), \(outputCGImage.width)x\(outputCGImage.height), alpha=\(outputCGImage.alphaInfo.rawValue)")
} catch {
    FileHandle.standardError.write("subject-lift: masked image generation failed: \(error)\n".data(using: .utf8)!)
    exit(1)
}
