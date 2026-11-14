Pod::Spec.new do |s|
  s.name           = 'MetaGlasses'
  s.version        = '1.0.0'
  s.summary        = 'Ray-Ban Meta glasses (Meta Wearables DAT 1.0.1) for the BrightBlind app'
  s.description    = 'Camera (photo + stream), capture button and speaker of Ray-Ban Meta glasses, exposed to JS.'
  s.author         = ''
  s.homepage       = 'https://docs.expo.dev/modules/'
  s.license        = 'MIT'
  s.platforms      = { :ios => '17.2' }
  s.source         = { git: '' }
  s.static_framework = true
  s.swift_version  = '5.9'

  s.dependency 'ExpoModulesCore'

  # Run ../fetch-sdk.sh first: the binaries are not in git.
  s.vendored_frameworks = 'Frameworks/MWDATCore.xcframework', 'Frameworks/MWDATCamera.xcframework', 'Frameworks/MWDATInputs.xcframework'
  s.frameworks = 'AVFoundation', 'AudioToolbox', 'UIKit'

  s.pod_target_xcconfig = {
    'DEFINES_MODULE' => 'YES'
  }

  s.source_files = "*.{h,m,mm,swift}"
end
